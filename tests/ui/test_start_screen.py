import os
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from apartment_planner.persistence import library as library_module
from apartment_planner.persistence.library import Library
from apartment_planner.ui import dialogs
from apartment_planner.ui import start_screen as start_screen_module
from apartment_planner.ui.start_screen import StartScreen
from tests.factories import write_project


@pytest.fixture
def screen(qtbot: QtBot, settings: QSettings, folder: Path) -> StartScreen:
    os.utime(write_project(folder / "Old.apartment"), (1_700_000_000, 1_700_000_000))
    os.utime(write_project(folder / "Flat.apartment"), (1_700_001_000, 1_700_001_000))
    screen = StartScreen(Library(settings))
    qtbot.addWidget(screen)
    return screen


def names(screen: StartScreen) -> list[str]:
    return [item.text(0) for item in screen._items()]


def test_lists_projects_newest_first_and_opens_on_activation(
    qtbot: QtBot, screen: StartScreen, folder: Path
) -> None:
    assert names(screen) == ["Flat", "Old"]

    with qtbot.waitSignal(screen.open_requested) as opened:
        screen.projects.itemActivated.emit(screen.projects.currentItem(), 0)

    assert opened.args == [folder / "Flat.apartment"]


def test_rename_selects_the_renamed_project(
    screen: StartScreen, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dialogs, "ask_project_name", lambda *args: "Home")

    screen.buttons["Rename…"].click()

    assert names(screen) == ["Home", "Old"]
    assert screen.selected_path() == folder / "Home.apartment"


def test_rename_to_a_taken_name_explains_why_it_failed(
    screen: StartScreen, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors: list[str] = []
    monkeypatch.setattr(dialogs, "ask_project_name", lambda *args: "Old")
    monkeypatch.setattr(dialogs, "show_error", lambda parent, title, text: errors.append(text))

    screen.buttons["Rename…"].click()

    assert errors == ['A file named "Old.apartment" already exists. Choose another name.']
    assert names(screen) == ["Flat", "Old"]


def test_duplicate_selects_the_new_copy(screen: StartScreen, folder: Path) -> None:
    screen.buttons["Duplicate"].click()

    assert names(screen) == ["Flat copy", "Flat", "Old"]
    assert screen.selected_path() == folder / "Flat copy.apartment"


@pytest.mark.parametrize("confirmed", [True, False])
def test_delete_moves_to_the_trash_only_after_confirmation(
    screen: StartScreen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, confirmed: bool
) -> None:
    trashed: list[str] = []

    def fake_trash(path: Path) -> bool:
        trashed.append(path.name)
        path.unlink()
        return True

    monkeypatch.setattr(dialogs, "confirm", lambda *args: confirmed)
    monkeypatch.setattr(
        start_screen_module,
        "delete_project",
        lambda path: library_module.delete_project(path, trash=fake_trash),
    )

    screen.buttons["Delete…"].click()

    assert trashed == (["Flat.apartment"] if confirmed else [])
    assert names(screen) == (["Old"] if confirmed else ["Flat", "Old"])
