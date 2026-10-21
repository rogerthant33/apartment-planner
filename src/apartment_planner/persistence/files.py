"""Reading and atomically writing project files on disk."""

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from apartment_planner.persistence.archive import ProjectFile, decode, encode
from apartment_planner.persistence.errors import NotAProjectError, ReadError

SUFFIX = ".apartment"


@dataclass(frozen=True)
class Fingerprint:
    """What a file looked like when we last read or wrote it."""

    size: int
    mtime_ns: int
    sha256: str

    @classmethod
    def of(cls, path: Path) -> "Fingerprint":
        data = path.read_bytes()
        return cls._of_bytes(path, data)

    @classmethod
    def _of_bytes(cls, path: Path, data: bytes) -> "Fingerprint":
        stat = path.stat()
        return cls(stat.st_size, stat.st_mtime_ns, hashlib.sha256(data).hexdigest())

    def matches(self, path: Path) -> bool:
        """True if the file still has this content. Hashes only when size or mtime moved."""
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        if (stat.st_size, stat.st_mtime_ns) == (self.size, self.mtime_ns):
            return True
        return stat.st_size == self.size and Fingerprint.of(path).sha256 == self.sha256


@dataclass(frozen=True)
class Loaded:
    project: ProjectFile
    fingerprint: Fingerprint


def read_project(path: Path) -> Loaded:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ReadError(path, error.strerror or str(error)) from error
    try:
        project = decode(data)
    except NotAProjectError as error:
        raise NotAProjectError(path) from error
    return Loaded(project, Fingerprint._of_bytes(path, data))


def write_atomic(path: Path, data: bytes) -> Fingerprint:
    """Write via a temporary file in the same folder, so `path` is never half-written."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return Fingerprint._of_bytes(path, data)


def backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def conflict_path(path: Path, now: datetime) -> Path:
    stem = path.name.removesuffix(SUFFIX)
    candidate = path.with_name(f"{stem} (conflict {now:%Y-%m-%d %H%M}){SUFFIX}")
    n = 2
    while candidate.exists():
        candidate = path.with_name(f"{stem} (conflict {now:%Y-%m-%d %H%M}) {n}{SUFFIX}")
        n += 1
    return candidate


@dataclass(frozen=True)
class Saved:
    path: Path  # where the project now lives (a conflict copy if there was a conflict)
    fingerprint: Fingerprint
    conflict: bool


def save_project(
    path: Path,
    project: ProjectFile,
    expected: Fingerprint | None,
    *,
    make_backup: bool,
    now: datetime,
) -> Saved:
    """Save `project` to `path` unless the file changed on disk since `expected`.

    `expected` is None for a file that shouldn't exist yet. On a conflict the
    project goes to a new conflict copy and the original is left untouched.
    """
    on_disk_unchanged = expected.matches(path) if expected else not path.exists()
    if not on_disk_unchanged:
        target = conflict_path(path, now)
        return Saved(target, write_atomic(target, encode(project)), conflict=True)
    if make_backup and path.exists():
        shutil.copy2(path, backup_path(path))
    return Saved(path, write_atomic(path, encode(project)), conflict=False)
