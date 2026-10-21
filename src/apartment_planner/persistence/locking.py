"""Edit locks on project files, so two people sharing a folder don't both edit
the same project. See docs/SPEC.md §8.
"""

from pathlib import Path

from PySide6.QtCore import QLockFile, QSysInfo

from apartment_planner.persistence.errors import ProjectFileError


class ProjectLockedError(ProjectFileError):
    """Someone else has the project open."""

    def __init__(self, path: Path, holder: str) -> None:
        self.holder = holder
        super().__init__(f'"{path.stem}" is open on {holder}. Close it there, then try again.')


class LockUnavailableError(ProjectFileError):
    """The lock file can't be created, usually because the folder is read-only."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"\"{path.stem}\" can't be edited because its folder doesn't allow new files. "
            "Check that you can change files there, or save a copy somewhere else."
        )


def lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def describe_holder(host: str, this_host: str) -> str:
    if host == this_host:
        return "this computer in another Apartment Planner window"
    return f'"{host}"' if host else "another computer"


class ProjectLock:
    """An exclusive lock on one project file, held in `<name>.apartment.lock`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = QLockFile(str(lock_path(path)))
        # Never treat a lock as stale because of its age: a project can stay open
        # for days. QLockFile still clears a lock whose process has died on this
        # computer, which covers crashes.
        self._file.setStaleLockTime(0)

    def acquire(self) -> None:
        """Take the lock, or raise ProjectLockedError / LockUnavailableError."""
        if self._file.tryLock(0):
            return
        if self._file.error() == QLockFile.LockError.LockFailedError:
            _pid, host, _app = self._file.getLockInfo()
            raise ProjectLockedError(self.path, describe_holder(host, QSysInfo.machineHostName()))
        raise LockUnavailableError(self.path)

    def release(self) -> None:
        self._file.unlock()

    @property
    def held(self) -> bool:
        return self._file.isLocked()
