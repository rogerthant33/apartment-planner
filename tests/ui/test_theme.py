from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from apartment_planner.canvas import style
from apartment_planner.model import new_project
from apartment_planner.state.rooms import add_room
from apartment_planner.ui.export import export_png
from apartment_planner.ui.main_window import MainWindow
from apartment_planner.ui.theme import DARK_KEY
from tests.factories import NOW


@pytest.fixture
def window(qtbot: QtBot, settings: QSettings) -> Iterator[MainWindow]:
    window = MainWindow(settings)
    qtbot.addWidget(window)
    yield window
    window.set_dark(False)


def test_dark_mode_is_remembered_and_used_by_the_canvas(
    window: MainWindow, settings: QSettings, qtbot: QtBot
) -> None:
    window.theme_action.trigger()

    assert style.is_dark()
    padlock = window.lock_action.icon().pixmap(32, 32).toImage()
    assert padlock.pixelColor(16, 22).name() == "#e2e2dc"  # light text colour on dark
    assert settings.value(DARK_KEY) in (True, "true")
    again = MainWindow(settings)
    qtbot.addWidget(again)
    assert again.theme_action.isChecked()


def test_exports_are_light_in_dark_mode(window: MainWindow, tmp_path: Path) -> None:
    doc, _ = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    export_png(doc, tmp_path / "light.png")

    window.set_dark(True)
    export_png(doc, tmp_path / "dark.png")

    assert (tmp_path / "dark.png").read_bytes() == (tmp_path / "light.png").read_bytes()
    assert style.is_dark()  # the screen stays dark
