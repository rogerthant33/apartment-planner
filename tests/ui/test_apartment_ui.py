from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from apartment_planner.model import DoorSpec, Opening, RectShape, new_project
from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.files import create_project_file
from apartment_planner.state.editor import EditorState
from apartment_planner.state.furniture import add_furniture
from apartment_planner.state.openings import add_opening, update_opening
from apartment_planner.state.rooms import add_room
from apartment_planner.ui.main_window import MainWindow
from tests.factories import NOW


@pytest.fixture
def window(qtbot: QtBot, settings: QSettings, folder: Path) -> Iterator[MainWindow]:
    """A project with one 400 by 300 cm room and a door on its top wall. It opens
    with the apartment locked."""
    doc, room_id = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    doc, _ = add_opening(doc, "door", room_id, doc.apartment.rooms[0].vertices[0].id, 100)
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


def door(window: MainWindow) -> Opening:
    return editor(window).doc.apartment.openings[0]


def test_apartment_tools_wait_for_unlocking(window: MainWindow) -> None:
    column = window.obstacle_actions[0]
    assert not column.isEnabled()

    window.lock_action.trigger()
    column.trigger()

    (added,) = editor(window).doc.apartment.obstacles
    assert editor(window).selection == {added.id}
    page = window.properties.furniture_page
    assert window.properties.currentWidget() is page
    assert page.title.text() == "Obstacle (part of the apartment)"
    assert page.fields["category"].isHidden()
    assert not page.locked.isVisible()


def test_locking_leaves_the_door_tool(window: MainWindow) -> None:
    window.lock_action.trigger()
    window.set_tool("door")

    window.lock_action.trigger()

    assert window.view.tool is window.view.tools["select"]


def test_opening_page_edits_the_selected_door(window: MainWindow) -> None:
    window.lock_action.trigger()
    editor(window).select({door(window).id})
    page = window.properties.opening_page
    assert window.properties.currentWidget() is page
    assert page.wall.text() == "Room 1, edge 1"

    page.swing.setCurrentIndex(1)
    page.swing.activated.emit(1)
    page.width_field.setText("5 m")
    page.width_field.editingFinished.emit()

    assert door(window).door == DoorSpec(hinge="start", swing="out")
    assert (
        page.error.text() == "Width: enter a length greater than 0 and at most the wall's 400 cm."
    )
    assert page.width_field.text() == "80 cm"

    page.kind.setCurrentIndex(1)
    page.kind.activated.emit(1)
    assert (door(window).kind, door(window).door) == ("window", None)
    assert page.hinge.isHidden()
    page.buttons["Delete"].click()
    assert editor(window).doc.apartment.openings == ()


def test_locked_apartment_shows_the_door_read_only(window: MainWindow) -> None:
    editor(window).select({door(window).id})

    assert not window.properties.opening_page.kind.isEnabled()


def test_doorway_clearance_setting_controls_doorway_warnings(window: MainWindow) -> None:
    doc = update_opening(
        editor(window).doc, door(window).id, door=DoorSpec(hinge="start", swing="out")
    )
    doc, _ = add_furniture(doc, RectShape(width=20, depth=20), (100, 30), "Stool")
    editor(window).commit(doc)
    assert [f.kind for f in window.view.findings] == ["doorway"]
    page = window.properties.settings_page

    page.doorway.setText("wide")
    page.doorway.editingFinished.emit()
    assert page.error.text() == "Doorway clearance: enter a length such as 60, or 0 for none."
    page.doorway.setText("0")
    page.doorway.editingFinished.emit()

    assert window.findings.summary.text() == "Everything fits."
    assert editor(window).doc.settings.default_clearance == 0


def test_locked_rooms_are_chosen_from_the_list_read_only_and_stay_selected(
    window: MainWindow,
) -> None:
    (room,) = editor(window).doc.apartment.rooms
    rooms = window.tools.rooms

    rooms.itemClicked.emit(rooms.item(0))
    page = window.properties.room_page
    assert editor(window).selection == {room.id}
    assert (rooms.isEnabled(), page.name.isEnabled()) == (True, False)
    window.lock_action.trigger()  # unlock
    assert page.name.isEnabled()
    window.lock_action.trigger()  # lock again

    assert editor(window).selection == {room.id}
    assert not page.name.isEnabled()
