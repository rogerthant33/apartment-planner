"""The projects folder, recent files, and project management on whole files:
new, rename, duplicate, save a copy and delete. See docs/SPEC.md §3 and §8.
"""

import os
import re
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFile, QSettings, QStandardPaths

from apartment_planner.model import new_id, new_project
from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.errors import ProjectFileError
from apartment_planner.persistence.files import (
    SUFFIX,
    backup_path,
    create_project_file,
    move_project_file,
    read_project,
)
from apartment_planner.persistence.locking import ProjectLock
from apartment_planner.persistence.session import ProjectSession

MAX_RECENT = 10
MAX_NAME_LENGTH = 100
_FORBIDDEN_CHARACTERS = '<>:"/\\|?*'
# Names Windows reserves for devices, with or without an extension.
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.IGNORECASE)


def name_problem(name: str) -> str | None:
    """Why `name` can't be a project file name on Windows or macOS, or None if it can."""
    if not name.strip():
        return "Enter a name."
    if name != name.strip():
        return "Names can't start or end with a space."
    if any(c in _FORBIDDEN_CHARACTERS or ord(c) < 32 for c in name):
        return f"Names can't contain any of {' '.join(_FORBIDDEN_CHARACTERS)}"
    if name.endswith("."):
        return "Names can't end with a dot."
    if _RESERVED.match(name):
        return f'"{name}" is reserved by Windows. Choose another name.'
    if len(name) > MAX_NAME_LENGTH:
        return f"Names can be at most {MAX_NAME_LENGTH} characters long."
    return None


class InvalidNameError(ProjectFileError):
    pass


def file_name_part(text: str) -> str:
    """`text` made safe to use in a file name: characters that aren't allowed in
    one on Windows or macOS become "-"."""
    return "".join("-" if c in _FORBIDDEN_CHARACTERS or ord(c) < 32 else c for c in text)


def project_name(path: Path) -> str:
    return path.name.removesuffix(SUFFIX)


def project_path(folder: Path, name: str) -> Path:
    if (problem := name_problem(name)) is not None:
        raise InvalidNameError(problem)
    return folder / f"{name}{SUFFIX}"


def unused_path(folder: Path, name: str) -> Path:
    """`<name>.apartment`, or `<name> 2.apartment` and so on if that's taken."""
    candidate = folder / f"{name}{SUFFIX}"
    n = 2
    while candidate.exists():
        candidate = folder / f"{name} {n}{SUFFIX}"
        n += 1
    return candidate


@dataclass(frozen=True)
class ProjectEntry:
    path: Path
    modified: datetime

    @property
    def name(self) -> str:
        return project_name(self.path)


def list_projects(folder: Path, recent: Iterable[Path]) -> list[ProjectEntry]:
    """Projects in `folder` plus recent ones from elsewhere, newest first."""
    paths = [p for p in folder.glob(f"*{SUFFIX}") if p.is_file()] if folder.is_dir() else []
    seen = {os.path.normcase(p.resolve()) for p in paths}
    for path in recent:
        if path.is_file() and os.path.normcase(path.resolve()) not in seen:
            paths.append(path)
    entries = []
    for path in paths:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue  # deleted since the listing
        entries.append(ProjectEntry(path, datetime.fromtimestamp(mtime).astimezone()))
    return sorted(entries, key=lambda e: (-e.modified.timestamp(), e.name.casefold()))


def with_recent(paths: list[str], path: str) -> list[str]:
    """`paths` with `path` moved to the front, capped at MAX_RECENT."""
    return [path, *(p for p in paths if p != path)][:MAX_RECENT]


class Library:
    """The projects folder and the recent-files list, kept in QSettings."""

    FOLDER_KEY = "projects_folder"
    RECENT_KEY = "recent_projects"

    def __init__(self, settings: QSettings) -> None:
        self._settings = settings

    @property
    def folder(self) -> Path:
        value = self._settings.value(self.FOLDER_KEY, "", type=str)
        return Path(str(value)) if value else default_projects_folder()

    @folder.setter
    def folder(self, path: Path) -> None:
        self._settings.setValue(self.FOLDER_KEY, str(path))

    def recent(self) -> list[Path]:
        return [Path(p) for p in self._recent_strings()]

    def add_recent(self, path: Path) -> None:
        self._set_recent(with_recent(self._recent_strings(), str(path.absolute())))

    def remove_recent(self, path: Path) -> None:
        key = str(path.absolute())
        self._set_recent([p for p in self._recent_strings() if p != key])

    def replace_recent(self, old: Path, new: Path) -> None:
        """After a rename: `new` takes `old`'s place, if `old` was recent."""
        old_key, new_key = str(old.absolute()), str(new.absolute())
        renamed = [new_key if p == old_key else p for p in self._recent_strings()]
        self._set_recent(list(dict.fromkeys(renamed)))

    def entries(self) -> list[ProjectEntry]:
        return list_projects(self.folder, self.recent())

    def _recent_strings(self) -> list[str]:
        value = self._settings.value(self.RECENT_KEY, [], type=list)
        return [str(p) for p in value] if isinstance(value, list) else []

    def _set_recent(self, paths: list[str]) -> None:
        self._settings.setValue(self.RECENT_KEY, paths)


def default_projects_folder() -> Path:
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(documents) / "Apartment Planner"


def create_project(folder: Path, name: str, now: datetime) -> tuple[ProjectFile, ProjectSession]:
    """A new empty project in `folder`, opened for editing."""
    path = project_path(folder, name)
    folder.mkdir(parents=True, exist_ok=True)
    project = ProjectFile(new_project(name, now=now))
    return project, ProjectSession.create(path, project)


def save_copy(project: ProjectFile, path: Path) -> None:
    """Write `project` to a new file as a separate project with its own ID."""
    doc = project.doc.evolve(id=new_id(), name=project_name(path))
    create_project_file(path, ProjectFile(doc, project.assets))


def duplicate_project(path: Path) -> Path:
    target = unused_path(path.parent, f"{project_name(path)} copy")
    save_copy(read_project(path).project, target)
    return target


def rename_project(path: Path, name: str) -> Path:
    """Rename a closed project. Refused while someone has it open."""
    target = project_path(path.parent, name)
    with _locked(path):
        move_project_file(path, target)
    return target


def move_to_trash(path: Path) -> bool:
    return QFile(str(path)).moveToTrash()


def delete_project(path: Path, *, trash: Callable[[Path], bool] = move_to_trash) -> None:
    """Move a closed project and its backup to the trash. Refused while someone has it open."""
    with _locked(path):
        for file in (path, backup_path(path)):
            if file.exists() and not trash(file):
                raise ProjectFileError(
                    f"Couldn't move \"{file.name}\" to the trash. Check that it isn't open in "
                    "another program and that you can change files in its folder."
                )


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    lock = ProjectLock(path)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
