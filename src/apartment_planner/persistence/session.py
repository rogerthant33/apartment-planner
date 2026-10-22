"""An open project file: where it lives, its edit lock, and what we last read or
wrote there.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Self

from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.errors import ProjectFileError
from apartment_planner.persistence.files import (
    Fingerprint,
    Saved,
    create_project_file,
    move_project_file,
    read_project,
    save_project,
)
from apartment_planner.persistence.locking import (
    LockUnavailableError,
    ProjectLock,
    ProjectLockedError,
)

log = logging.getLogger(__name__)


class ReadOnlyError(ProjectFileError):
    def __init__(self) -> None:
        super().__init__("This project is open read-only. Save an editable copy to make changes.")


class ProjectSession:
    """Saves go through here, so the conflict check and `.bak` are never skipped."""

    def __init__(
        self,
        path: Path,
        fingerprint: Fingerprint,
        lock: ProjectLock | None,
        *,
        read_only_reason: str | None = None,
        backed_up: bool = False,
    ) -> None:
        self.path = path
        self.fingerprint = fingerprint
        self.read_only_reason = read_only_reason
        self._lock = lock
        self._backed_up = backed_up

    @classmethod
    def open(cls, path: Path) -> tuple[ProjectFile, Self]:
        """Load a project, opening it read-only if someone else has it open."""
        lock = ProjectLock(path)
        reason = None
        try:
            lock.acquire()
        except ProjectLockedError as error:
            reason = f"This project is open on {error.holder}, so it opened read-only."
        except LockUnavailableError as error:
            reason = str(error)
        try:
            loaded = read_project(path)
        except BaseException:
            lock.release()
            raise
        held = lock if reason is None else None
        return loaded.project, cls(path, loaded.fingerprint, held, read_only_reason=reason)

    @classmethod
    def create(cls, path: Path, project: ProjectFile) -> Self:
        """Write a new project file and open it. Refuses to replace an existing file."""
        lock = ProjectLock(path)
        lock.acquire()
        try:
            fingerprint = create_project_file(path, project)
        except BaseException:
            lock.release()
            raise
        # A brand-new file has nothing worth backing up.
        return cls(path, fingerprint, lock, backed_up=True)

    @property
    def read_only(self) -> bool:
        return self.read_only_reason is not None

    def save(self, project: ProjectFile, now: datetime) -> Saved:
        """Save, or write a conflict copy and continue in it if the file changed on disk."""
        if self.read_only:
            raise ReadOnlyError()
        saved = save_project(
            self.path, project, self.fingerprint, make_backup=not self._backed_up, now=now
        )
        self._backed_up = True
        self.fingerprint = saved.fingerprint
        if saved.conflict:
            self._move_lock(saved.path)
            self.path = saved.path
        return saved

    def rename(self, target: Path) -> None:
        """Rename the project file (and its backup) while keeping it locked."""
        if self.read_only:
            raise ReadOnlyError()
        new_lock = None
        if not target.exists():  # a case-only rename keeps the same lock file
            new_lock = ProjectLock(target)
            new_lock.acquire()
        try:
            move_project_file(self.path, target)
        except BaseException:
            if new_lock is not None:
                new_lock.release()
            raise
        if new_lock is not None:
            self._release_lock()
            self._lock = new_lock
        self.path = target

    def close(self) -> None:
        self._release_lock()

    def _move_lock(self, target: Path) -> None:
        self._release_lock()
        lock = ProjectLock(target)
        try:
            lock.acquire()
        except ProjectFileError:
            # Nobody else can have a conflict copy open that we have only just written.
            log.warning("Couldn't lock %s", target, exc_info=True)
            return
        self._lock = lock

    def _release_lock(self) -> None:
        if self._lock is not None:
            self._lock.release()
            self._lock = None
