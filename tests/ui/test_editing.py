from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from apartment_planner.model import new_project
from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.files import create_project_file
from apartment_planner.state.editor import EditorState
from apartment_planner.state.rooms import add_room, room
from apartment_planner.ui.main_window import MainWindow
from tests.factories import NOW

SQUARE = [(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0)]


@pytest.fixture
def window(qtbot: QtBot, settings: QSettings, folder: Path) -> Iterator[MainWindow]:
    doc, _ = add_room(new_project("Flat", now=NOW), SQUARE)
    path = folder / "Flat.apartment"
    create_project_file(path, ProjectFile(doc))
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.show()
    window.open_path(path)
    yield window
    window.close_project()


def editor(window: MainWindow) -> EditorState:
    assert window.editor is not None
    return window.editor


def unlock_and_select_room(window: MainWindow) -> str:
    window.lock_action.setChecked(False)
    room_id = editor(window).doc.apartment.rooms[0].id
    editor(window).select({room_id})
    return room_id


def test_projects_with_rooms_open_locked_without_being_saved(
    window: MainWindow, folder: Path
) -> None:
    before = (folder / "Flat.apartment").read_bytes()

    assert window.lock_action.isChecked()
    assert not window.rect_tool_action.isEnabled()
    window.save_now()
    assert (folder / "Flat.apartment").read_bytes() == before


def test_locking_is_not_undone_with_edits(window: MainWindow) -> None:
    room_id = unlock_and_select_room(window)
    window.duplicate_action.trigger()
    assert len(editor(window).doc.apartment.rooms) == 2
    window.lock_action.setChecked(True)

    window.undo_action.trigger()

    assert [r.id for r in editor(window).doc.apartment.rooms] == [room_id]
    assert editor(window).doc.settings.apartment_locked
    assert editor(window).selection == frozenset()
    assert window.redo_action.isEnabled()


def test_edge_length_field_moves_the_end_corner_on_enter(window: MainWindow) -> None:
    room_id = unlock_and_select_room(window)
    field = window.properties.room_page.edges[0]

    field.setText("2.5 m")
    field.editingFinished.emit()

    corners = [(v.x, v.y) for v in room(editor(window).doc, room_id).vertices]
    assert corners[1] == pytest.approx((250, 0))
    assert field.text() == "250 cm"


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("lots", "Edge 1: enter a length such as 250 or 2.5 m."),
        ("0", "Enter a length greater than 0."),
    ],
)
def test_bad_edge_lengths_are_rejected_inline(window: MainWindow, text: str, error: str) -> None:
    unlock_and_select_room(window)
    before = editor(window).doc
    page = window.properties.room_page

    page.edges[0].setText(text)
    page.edges[0].editingFinished.emit()

    assert editor(window).doc == before
    assert page.error.text() == error
    assert page.edges[0].text() == "400 cm"


def test_room_name_field_renames_on_enter(window: MainWindow) -> None:
    room_id = unlock_and_select_room(window)
    page = window.properties.room_page

    page.name.setText("Kitchen")
    page.name.editingFinished.emit()

    assert room(editor(window).doc, room_id).name == "Kitchen"
    assert window.tools.rooms.item(0).text() == "Kitchen"


def test_settings_change_grid_and_units_without_undo(window: MainWindow) -> None:
    page = window.properties.settings_page
    assert window.properties.currentWidget() is page

    page.unit.setCurrentText("m")
    page.grid.setText("0.25")
    page.grid.editingFinished.emit()

    settings = editor(window).doc.settings
    assert (settings.display_unit, settings.grid_size) == ("m", 25)
    assert window.view.plan.grid_size == 25
    assert not editor(window).can_undo


def test_delete_action_removes_the_selected_room(window: MainWindow) -> None:
    unlock_and_select_room(window)

    window.delete_action.trigger()

    assert editor(window).doc.apartment.rooms == ()
    assert not window.delete_action.isEnabled()


def test_single_key_shortcuts_are_typed_into_text_fields(window: MainWindow) -> None:
    window.lock_action.setChecked(False)
    field = window.properties.settings_page.grid
    field.setFocus()
    field.clear()

    for key in (Qt.Key.Key_M, Qt.Key.Key_P, Qt.Key.Key_0):
        QTest.keyClick(field, key)

    assert field.text() == "mp0"
    assert window.select_tool_action.isChecked()
    QTest.keyClick(window.view, Qt.Key.Key_M)
    assert window.rect_tool_action.isChecked()


def test_clicking_a_room_in_the_list_selects_it(window: MainWindow) -> None:
    window.lock_action.setChecked(False)
    rooms = window.tools.rooms
    rect = rooms.visualItemRect(rooms.item(0))

    QTest.mouseClick(
        rooms.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier(0), rect.center()
    )

    assert editor(window).selection == {editor(window).doc.apartment.rooms[0].id}
    assert window.properties.currentWidget() is window.properties.room_page
