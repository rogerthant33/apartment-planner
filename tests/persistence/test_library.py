import os
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.errors import ProjectExistsError, ProjectFileError
from apartment_planner.persistence.files import backup_path, create_project_file, read_project
from apartment_planner.persistence.library import (
    MAX_RECENT,
    InvalidNameError,
    Library,
    create_project,
    default_projects_folder,
    delete_project,
    duplicate_project,
    file_name_part,
    list_projects,
    name_problem,
    rename_project,
    with_recent,
)
from apartment_planner.persistence.locking import ProjectLock, ProjectLockedError, lock_path
from tests.factories import NOW, full_project


def make(path: Path, mtime: float = 1_700_000_000.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = full_project().evolve(name=path.stem)
    assert doc.background is not None
    create_project_file(path, ProjectFile(doc, {doc.background.asset_id: b"image"}))
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return Library(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))


@pytest.mark.parametrize("name", ["Flat", "Flat 2 (old)", "Wohnung Köln", "a" * 100])
def test_accepts_ordinary_names(name: str) -> None:
    assert name_problem(name) is None


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("", "Enter a name"),
        ("   ", "Enter a name"),
        (" Flat", "start or end with a space"),
        ("Flat/2", "can't contain"),
        ("Flat: old", "can't contain"),
        ("Flat\t2", "can't contain"),
        ("Flat.", "end with a dot"),
        ("CON", "reserved by Windows"),
        ("lpt1.backup", "reserved by Windows"),
        ("a" * 101, "at most 100"),
    ],
)
def test_rejects_names_that_are_not_portable_file_names(name: str, problem: str) -> None:
    assert problem in (name_problem(name) or "")


def test_lists_projects_and_recent_files_newest_first(tmp_path: Path) -> None:
    folder = tmp_path / "Projects"
    old = make(folder / "Old.apartment", mtime=1_700_000_000)
    new = make(folder / "New.apartment", mtime=1_700_003_000)
    elsewhere = make(tmp_path / "Shared" / "Shared.apartment", mtime=1_700_002_000)
    backup_path(new).write_bytes(b"backup")
    (folder / "notes.txt").write_text("not a project")

    entries = list_projects(folder, [new, elsewhere, tmp_path / "Gone.apartment"])

    assert [e.path for e in entries] == [new, elsewhere, old]
    assert entries[1].name == "Shared"


def test_recent_files_move_to_the_front_without_duplicates() -> None:
    paths = [str(n) for n in range(MAX_RECENT)]

    assert with_recent(paths, "3")[:4] == ["3", "0", "1", "2"]
    assert with_recent(paths, "new") == ["new", *paths[:-1]]


def test_library_remembers_folder_and_recent_files(library: Library, tmp_path: Path) -> None:
    assert library.folder == default_projects_folder()
    a, b, c = (tmp_path / f"{name}.apartment" for name in "abc")

    library.folder = tmp_path
    library.add_recent(a)
    library.add_recent(b)
    library.add_recent(a)
    library.remove_recent(b)
    library.add_recent(b)
    library.replace_recent(a, c)
    library.add_recent(a)
    library.replace_recent(a, b)

    assert library.folder == tmp_path
    assert library.recent() == [b, c]


def test_create_project_makes_the_folder_and_opens_the_new_file(tmp_path: Path) -> None:
    folder = tmp_path / "Apartment Planner"

    project, session = create_project(folder, "Flat", NOW)

    assert session.path == folder / "Flat.apartment"
    assert read_project(session.path).project == project
    assert project.doc.name == "Flat"
    assert lock_path(session.path).exists()


def test_create_project_refuses_bad_or_taken_names(tmp_path: Path) -> None:
    make(tmp_path / "Flat.apartment")

    with pytest.raises(InvalidNameError, match="can't contain"):
        create_project(tmp_path, "Flat/2", NOW)
    with pytest.raises(ProjectExistsError):
        create_project(tmp_path, "Flat", NOW)


def test_duplicates_are_new_projects_with_numbered_names(tmp_path: Path) -> None:
    original = make(tmp_path / "Flat.apartment")

    first = duplicate_project(original)
    second = duplicate_project(original)

    source = read_project(original).project
    copy = read_project(first).project
    assert [first.name, second.name] == ["Flat copy.apartment", "Flat copy 2.apartment"]
    assert copy.doc.id != source.doc.id
    assert copy.doc.name == "Flat copy"
    assert copy.doc.apartment == source.doc.apartment
    assert copy.assets == source.assets


def test_rename_renames_the_file_and_its_backup(tmp_path: Path) -> None:
    path = make(tmp_path / "Flat.apartment")
    backup_path(path).write_bytes(b"backup")

    target = rename_project(path, "Home")

    assert target == tmp_path / "Home.apartment"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Home.apartment", "Home.apartment.bak"]


def test_rename_and_delete_are_refused_while_the_project_is_open(tmp_path: Path) -> None:
    path = make(tmp_path / "Flat.apartment")
    lock = ProjectLock(path)
    lock.acquire()

    with pytest.raises(ProjectLockedError):
        rename_project(path, "Home")
    with pytest.raises(ProjectLockedError):
        delete_project(path, trash=lambda p: pytest.fail("trashed an open project"))
    lock.release()
    assert path.exists()


def test_delete_moves_the_project_and_its_backup_to_the_trash(tmp_path: Path) -> None:
    path = make(tmp_path / "Projects" / "Flat.apartment")
    backup_path(path).write_bytes(b"backup")
    trash = tmp_path / "Trash"
    trash.mkdir()

    def move_to_trash(file: Path) -> bool:
        file.rename(trash / file.name)
        return True

    delete_project(path, trash=move_to_trash)

    assert sorted(p.name for p in trash.iterdir()) == ["Flat.apartment", "Flat.apartment.bak"]
    assert list(path.parent.iterdir()) == []


def test_delete_reports_a_file_the_trash_refused(tmp_path: Path) -> None:
    path = make(tmp_path / "Flat.apartment")

    with pytest.raises(ProjectFileError, match=r'move "Flat\.apartment" to the trash'):
        delete_project(path, trash=lambda p: False)
    assert path.exists()


def test_file_name_part_replaces_characters_files_cannot_have() -> None:
    assert file_name_part('Plan: 1/2 "final"\tv2?') == "Plan- 1-2 -final--v2-"
    assert file_name_part("Küche & Bad (v2)") == "Küche & Bad (v2)"
