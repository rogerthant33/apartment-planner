from pathlib import Path

import pytest

from apartment_planner.model import new_project
from apartment_planner.persistence.archive import ProjectFile, encode
from apartment_planner.persistence.errors import NotAProjectError, ProjectExistsError
from apartment_planner.persistence.files import backup_path, read_project
from apartment_planner.persistence.locking import lock_path
from apartment_planner.persistence.session import ProjectSession, ReadOnlyError
from tests.factories import NOW


def project(name: str) -> ProjectFile:
    return ProjectFile(new_project(name, now=NOW))


def saved_name(path: Path) -> str:
    return read_project(path).project.doc.name


@pytest.fixture
def path(tmp_path: Path) -> Path:
    path = tmp_path / "Flat.apartment"
    path.write_bytes(encode(project("Original")))
    return path


def test_open_locks_the_project_until_closed(path: Path) -> None:
    loaded, session = ProjectSession.open(path)

    assert loaded.doc.name == "Original"
    assert not session.read_only
    assert lock_path(path).exists()
    session.close()
    assert not lock_path(path).exists()


def test_project_open_elsewhere_opens_read_only(path: Path) -> None:
    _, first = ProjectSession.open(path)

    _, second = ProjectSession.open(path)

    assert second.read_only_reason is not None
    assert "open on this computer in another" in second.read_only_reason
    with pytest.raises(ReadOnlyError):
        second.save(project("Mine"), NOW)
    second.close()
    assert lock_path(path).exists()  # still first's lock
    first.close()


def test_failed_open_leaves_no_lock(tmp_path: Path) -> None:
    notes = tmp_path / "Notes.apartment"
    notes.write_text("shopping list")

    with pytest.raises(NotAProjectError):
        ProjectSession.open(notes)
    assert not lock_path(notes).exists()


def test_only_the_first_save_makes_a_backup(path: Path) -> None:
    original = path.read_bytes()
    _, session = ProjectSession.open(path)

    session.save(project("First"), NOW)
    session.save(project("Second"), NOW)

    assert backup_path(path).read_bytes() == original
    assert saved_name(path) == "Second"


def test_after_a_conflict_saves_continue_in_the_conflict_copy(path: Path) -> None:
    _, session = ProjectSession.open(path)
    path.write_bytes(encode(project("Theirs")))

    first = session.save(project("Mine"), NOW)
    second = session.save(project("Mine again"), NOW)

    assert first.conflict
    assert not second.conflict
    assert session.path == first.path == second.path
    assert saved_name(path) == "Theirs"
    assert saved_name(session.path) == "Mine again"
    assert lock_path(session.path).exists()
    assert not lock_path(path).exists()


def test_new_project_refuses_existing_files_and_needs_no_backup(path: Path) -> None:
    with pytest.raises(ProjectExistsError):
        ProjectSession.create(path, project("Mine"))
    assert not lock_path(path).exists()

    session = ProjectSession.create(path.with_name("New.apartment"), project("New"))
    session.save(project("New, edited"), NOW)

    assert not backup_path(session.path).exists()


def test_rename_moves_the_file_and_the_lock(path: Path) -> None:
    _, session = ProjectSession.open(path)
    target = path.with_name("Home.apartment")

    session.rename(target)
    saved = session.save(project("Renamed"), NOW)

    assert not saved.conflict
    assert saved_name(target) == "Renamed"
    assert not path.exists()
    assert lock_path(target).exists()
    assert not lock_path(path).exists()
