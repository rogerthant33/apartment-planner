"""The project open in the window: its editor state, file session and autosave."""

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from apartment_planner.canvas.signals import EditorSignals
from apartment_planner.model import ProjectDoc, new_id
from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.autosave import SaveStatus
from apartment_planner.persistence.autosaver import Autosaver
from apartment_planner.persistence.library import project_name, project_path, save_copy
from apartment_planner.persistence.session import ProjectSession
from apartment_planner.state.editor import EditorState
from apartment_planner.state.rooms import with_default_lock

STATUS_TEXT = {
    SaveStatus.SAVED: "Saved",
    SaveStatus.PENDING: "Saving…",
    SaveStatus.SAVING: "Saving…",
    SaveStatus.FAILED: "Save failed — retrying",
}


def local_now() -> datetime:
    return datetime.now().astimezone()


class OpenProject(QObject):
    status_changed = Signal()
    renamed = Signal(Path)  # the old path
    conflict = Signal(Path, Path)  # the original file, the conflict copy now open

    def __init__(
        self,
        session: ProjectSession,
        project: ProjectFile,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = local_now,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        # The default lock is a view of the document, not an edit: it isn't saved
        # unless something else changes.
        self.editor = EditorState(with_default_lock(project.doc))
        self.signals = EditorSignals(self.editor, self)
        self._assets = project.assets
        self._now = now
        self._autosaver: Autosaver | None = None
        if not session.read_only:
            self._autosaver = Autosaver(self._save, clock=clock, parent=self)
            self._autosaver.status_changed.connect(self.status_changed)
            self.editor.on_document_changed(self._autosaver.changed)

    @property
    def doc(self) -> ProjectDoc:
        return self.editor.doc

    @property
    def path(self) -> Path:
        return self.session.path

    @property
    def assets(self) -> Mapping[str, bytes]:
        """Images by asset ID. Only those the document refers to are saved, so undo
        can bring back an earlier background."""
        return self._assets

    def add_asset(self, data: bytes) -> str:
        """Keep an image's bytes with the project; returns its new asset ID."""
        asset_id = new_id()
        self._assets[asset_id] = data
        return asset_id

    @property
    def name(self) -> str:
        return project_name(self.path)

    @property
    def read_only_reason(self) -> str | None:
        return self.session.read_only_reason

    def status(self) -> tuple[str, str]:
        """Status bar text, and the tooltip explaining it."""
        if self._autosaver is None:
            return "Read-only", self.read_only_reason or ""
        return STATUS_TEXT[self._autosaver.status], self._autosaver.error or ""

    @property
    def save_error(self) -> str | None:
        return self._autosaver.error if self._autosaver else None

    def flush(self) -> bool:
        """Save now if needed. True when nothing is left unsaved."""
        return self._autosaver is None or self._autosaver.flush()

    def rename(self, name: str) -> None:
        old = self.path
        self.session.rename(project_path(old.parent, name))
        self.editor.update_untracked(self.doc.evolve(name=name))
        self.renamed.emit(old)

    def save_copy(self, path: Path) -> None:
        save_copy(self._project(), path)

    def close(self) -> None:
        if self._autosaver is not None:
            self._autosaver.stop()
        self.session.close()

    def _project(self) -> ProjectFile:
        return ProjectFile(self.doc, self._assets)

    def _save(self) -> None:
        original = self.path
        now = self._now()
        doc = self.doc.evolve(updated_at=now.astimezone(UTC))
        saved = self.session.save(ProjectFile(doc, self._assets), now)
        if saved.conflict:
            self.conflict.emit(original, saved.path)
