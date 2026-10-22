from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from apartment_planner.model import new_project
from apartment_planner.persistence.archive import ProjectFile, encode
from apartment_planner.persistence.files import read_project
from apartment_planner.persistence.locking import ProjectLock
from apartment_planner.ui import dialogs
from apartment_planner.ui.dialogs import FailedSaveChoice
from apartment_planner.ui.main_window import APP_NAME, MainWindow
from apartment_planner.ui.open_project import OpenProject
from tests.factories import write_project


@pytest.fixture
def window(qtbot: QtBot, settings: QSettings) -> Iterator[MainWindow]:
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close_project()


def open_project(window: MainWindow) -> OpenProject:
    assert window.project is not None
    return window.project


def edit(project: OpenProject) -> None:
    doc = project.doc
    project.editor.commit(doc.evolve(layouts=(doc.layouts[0].evolve(name="Edited"),)))


def test_starts_on_the_start_screen(window: MainWindow) -> None:
    assert window.pages.currentWidget() is window.start_screen
    assert window.windowTitle() == APP_NAME
    assert window.save_status.text() == "No project open"
    assert not window.tools_panel.isVisible()
    assert not window.close_action.isEnabled()


def test_new_project_is_created_in_the_projects_folder_and_opened(
    window: MainWindow, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dialogs, "ask_project_name", lambda *args: "Flat")

    window.new_action.trigger()

    assert open_project(window).path == folder / "Flat.apartment"
    assert window.windowTitle() == f"Flat — {APP_NAME}"
    assert window.save_status.text() == "Saved"
    assert window.tools_panel.isVisible()
    assert window.library.recent() == [folder / "Flat.apartment"]


def test_save_now_writes_the_latest_document(window: MainWindow, folder: Path) -> None:
    path = write_project(folder / "Flat.apartment")
    window.open_path(path)
    project = open_project(window)
    project.editor.update_untracked(
        project.doc.evolve(settings=project.doc.settings.evolve(grid_size=25))
    )
    assert window.save_status.text() == "Saving…"

    window.save_action.trigger()

    assert read_project(path).project.doc.settings.grid_size == 25
    assert window.save_status.text() == "Saved"


def test_project_open_elsewhere_opens_read_only(window: MainWindow, folder: Path) -> None:
    path = write_project(folder / "Flat.apartment")
    lock = ProjectLock(path)
    lock.acquire()

    window.open_path(path)

    assert "open on this computer" in window.banner.label.text()
    assert window.banner.button.text() == "Save an Editable Copy…"
    assert window.save_status.text() == "Read-only"
    assert window.windowTitle() == f"Flat (read-only) — {APP_NAME}"
    assert not window.rename_action.isEnabled()
    lock.release()


def test_closing_while_saves_fail_asks_what_to_do(
    window: MainWindow, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.open_path(write_project(folder / "Flat.apartment"))
    project = open_project(window)

    def disk_full(*args: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(project.session, "save", disk_full)
    choices = iter([FailedSaveChoice.RETRY, FailedSaveChoice.CANCEL, FailedSaveChoice.DISCARD])
    asked: list[str] = []

    def ask(parent: object, name: str, reason: str) -> FailedSaveChoice:
        asked.append(reason)
        return next(choices)

    monkeypatch.setattr(dialogs, "ask_failed_save", ask)
    edit(project)

    assert not window.close_project()
    assert window.project is project
    assert window.save_status.text() == "Save failed — retrying"
    assert window.save_status.toolTip() == "No space left on device"

    assert window.close_project()
    assert window.project is None
    assert asked == ["No space left on device"] * 3


def test_conflicting_save_continues_in_a_copy_and_explains(
    window: MainWindow, folder: Path
) -> None:
    path = write_project(folder / "Flat.apartment")
    window.open_path(path)
    project = open_project(window)
    path.write_bytes(encode(ProjectFile(new_project("Theirs"))))

    edit(project)
    window.save_now()

    assert "changed by someone else" in window.banner.label.text()
    assert window.windowTitle().startswith("Flat (conflict ")
    assert read_project(path).project.doc.name == "Theirs"
    assert window.library.recent()[0] == project.path


def test_rename_renames_the_open_project(
    window: MainWindow, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.open_path(write_project(folder / "Flat.apartment"))
    monkeypatch.setattr(dialogs, "ask_project_name", lambda *args: "Home")

    window.rename_action.trigger()
    window.save_now()

    assert window.windowTitle() == f"Home — {APP_NAME}"
    assert read_project(folder / "Home.apartment").project.doc.name == "Home"
    assert window.library.recent() == [folder / "Home.apartment"]


def test_files_that_cannot_open_are_explained_and_left_alone(
    window: MainWindow, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors: list[str] = []
    monkeypatch.setattr(dialogs, "show_error", lambda parent, title, text: errors.append(text))
    notes = folder / "Notes.apartment"
    notes.write_text("shopping list")
    gone = folder / "Gone.apartment"
    window.library.add_recent(gone)

    assert not window.open_path(notes)
    assert not window.open_path(gone)

    assert errors[0] == '"Notes.apartment" isn\'t an Apartment Planner project.'
    assert errors[1].startswith('Couldn\'t read "Gone.apartment": ')
    assert notes.read_text() == "shopping list"
    assert window.project is None
    assert gone not in window.library.recent()
