"""Every button says what it does on hover (docs/SPEC.md §3)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QAbstractButton, QWidget
from pytestqt.qtbot import QtBot

from apartment_planner.model import RectShape
from apartment_planner.state.furniture import add_furniture
from apartment_planner.ui.main_window import MainWindow
from tests.factories import write_project


@pytest.fixture
def window(qtbot: QtBot, settings: QSettings, folder: Path) -> Iterator[MainWindow]:
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.show()
    yield window
    window.close_project()


def missing_tips(root: QWidget) -> list[str]:
    """Buttons whose hover text is empty or only repeats their label. Qt's own
    buttons, and ones with nothing on them yet (the banner's, until a message
    gives it an action), don't count."""
    missing = []
    for button in root.findChildren(QAbstractButton):
        if button.objectName().startswith("qt_") or not (button.text() or button.icon()):
            continue
        label = button.text().replace("&", "").removesuffix("…").strip()
        tip = button.toolTip().strip()
        if not tip or tip.removesuffix("…") == label:
            missing.append(label or button.objectName() or type(button).__name__)
    return missing


def test_every_button_explains_itself_on_hover(window: MainWindow, folder: Path) -> None:
    assert missing_tips(window.start_screen) == []

    window.open_path(write_project(folder / "Flat.apartment"))
    assert window.editor is not None
    doc, sofa = add_furniture(window.editor.doc, RectShape(width=200, depth=90), (0, 0), "Sofa")
    window.editor.commit(doc)
    pages = window.properties
    for selection in ((), {sofa}):  # every page gets built at least once
        window.editor.select(selection)
    pages.furniture_page.show()
    pages.selection_page.show()
    pages.rooms_page.show()
    pages.room_page.show()
    pages.opening_page.show()

    assert missing_tips(window) == []
