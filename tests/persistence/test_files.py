import os
from collections.abc import Callable
from pathlib import Path

import pytest

from apartment_planner.model import new_project
from apartment_planner.persistence.archive import ProjectFile, encode
from apartment_planner.persistence.errors import NotAProjectError, ProjectExistsError, ReadError
from apartment_planner.persistence.files import (
    Fingerprint,
    backup_path,
    conflict_path,
    create_project_file,
    move_project_file,
    read_project,
    save_project,
)
from tests.factories import NOW


def project(name: str = "Flat") -> ProjectFile:
    return ProjectFile(new_project(name, now=NOW))


def created(tmp_path: Path, name: str = "Flat") -> tuple[Path, Fingerprint]:
    path = tmp_path / f"{name}.apartment"
    return path, create_project_file(path, project(name))


def test_read_returns_what_was_written_and_its_fingerprint(tmp_path: Path) -> None:
    original = project()
    path = tmp_path / "Flat.apartment"
    fingerprint = create_project_file(path, original)

    loaded = read_project(path)

    assert loaded.project == original
    assert loaded.fingerprint == fingerprint


def test_create_refuses_to_replace_a_file(tmp_path: Path) -> None:
    path = tmp_path / "Flat.apartment"
    path.write_bytes(b"precious")

    with pytest.raises(ProjectExistsError, match=r'"Flat\.apartment" already exists'):
        create_project_file(path, project())
    assert path.read_bytes() == b"precious"


def test_save_keeps_the_previous_version_as_backup(tmp_path: Path) -> None:
    path, fingerprint = created(tmp_path)
    before = path.read_bytes()

    result = save_project(path, project("Mine"), fingerprint, make_backup=True, now=NOW)

    assert (result.path, result.conflict) == (path, False)
    assert result.fingerprint == Fingerprint.of(path)
    assert read_project(path).project.doc.name == "Mine"
    assert backup_path(path).read_bytes() == before


def test_save_without_backup_leaves_none(tmp_path: Path) -> None:
    path, fingerprint = created(tmp_path)

    save_project(path, project("Mine"), fingerprint, make_backup=False, now=NOW)

    assert not backup_path(path).exists()


def edit(path: Path) -> None:
    path.write_bytes(encode(project("Theirs")))


def delete(path: Path) -> None:
    path.unlink()


@pytest.mark.parametrize("external_change", [edit, delete])
def test_file_changed_on_disk_gets_a_conflict_copy_instead(
    tmp_path: Path, external_change: Callable[[Path], None]
) -> None:
    path, fingerprint = created(tmp_path)
    external_change(path)
    theirs = path.read_bytes() if path.exists() else None

    result = save_project(path, project("Mine"), fingerprint, make_backup=True, now=NOW)

    assert result.conflict
    assert result.path.name == "Flat (conflict 2026-10-21 1200).apartment"
    assert read_project(result.path).project.doc.name == "Mine"
    assert (path.read_bytes() if path.exists() else None) == theirs
    assert not backup_path(path).exists()


def test_save_of_a_new_project_never_replaces_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "Flat.apartment"
    path.write_bytes(b"precious")

    result = save_project(path, project(), None, make_backup=True, now=NOW)

    assert result.conflict
    assert path.read_bytes() == b"precious"


def test_conflict_copies_never_replace_each_other(tmp_path: Path) -> None:
    path = tmp_path / "Flat.apartment"
    conflict_path(path, NOW).touch()

    assert conflict_path(path, NOW).name == "Flat (conflict 2026-10-21 1200) 2.apartment"


def test_fingerprint_ignores_touches_but_not_same_size_edits(tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"aaaa")
    fingerprint = Fingerprint.of(path)
    later = fingerprint.mtime_ns + 10**9

    os.utime(path, ns=(later, later))
    assert fingerprint.matches(path)

    path.write_bytes(b"bbbb")
    os.utime(path, ns=(later, later))
    assert not fingerprint.matches(path)


def test_failed_replace_keeps_the_previous_file_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, fingerprint = created(tmp_path)
    before = path.read_bytes()

    def deny(src: object, dst: object) -> None:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(os, "replace", deny)

    with pytest.raises(PermissionError):
        save_project(path, project("Mine"), fingerprint, make_backup=False, now=NOW)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_read_errors_name_the_file(tmp_path: Path) -> None:
    with pytest.raises(ReadError, match=r'"Missing\.apartment"'):
        read_project(tmp_path / "Missing.apartment")

    notes = tmp_path / "Notes.apartment"
    notes.write_text("shopping list")
    with pytest.raises(NotAProjectError, match=r'"Notes\.apartment"'):
        read_project(notes)


def test_move_renames_the_file_and_its_backup(tmp_path: Path) -> None:
    path, _ = created(tmp_path)
    backup_path(path).write_bytes(b"old")

    move_project_file(path, tmp_path / "Home.apartment")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["Home.apartment", "Home.apartment.bak"]


def test_move_refuses_to_replace_another_project(tmp_path: Path) -> None:
    path, _ = created(tmp_path, "Flat")
    other, _ = created(tmp_path, "Home")

    with pytest.raises(ProjectExistsError):
        move_project_file(path, other)
    assert read_project(other).project.doc.name == "Home"
