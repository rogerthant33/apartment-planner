from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from apartment_planner.model import FurnitureItem, RectShape, new_project
from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.files import create_project_file
from apartment_planner.state.editor import EditorState
from apartment_planner.state.rooms import add_room
from apartment_planner.ui import dialogs
from apartment_planner.ui.main_window import MainWindow
from tests.factories import NOW


@pytest.fixture
def window(qtbot: QtBot, settings: QSettings, folder: Path) -> Iterator[MainWindow]:
    doc, _ = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
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


def furniture(window: MainWindow) -> list[FurnitureItem]:
    return list(editor(window).doc.active_layout.furniture)


def add_table(window: MainWindow) -> FurnitureItem:
    window.add_actions[0].trigger()
    return furniture(window)[-1]


def test_added_furniture_is_selected_and_shown_in_the_panel(window: MainWindow) -> None:
    table = add_table(window)

    assert (table.name, table.shape) == ("Table", RectShape(width=120, depth=80))
    assert editor(window).selection == {table.id}
    assert window.properties.currentWidget() is window.properties.furniture_page
    assert window.properties.furniture_page.fields["width"].text() == "120 cm"


def test_width_field_commits_and_refuses_bad_values_inline(window: MainWindow) -> None:
    table = add_table(window)
    page = window.properties.furniture_page

    page.fields["width"].setText("1.6 m")
    page.fields["width"].editingFinished.emit()
    page.fields["depth"].setText("wide")
    page.fields["depth"].editingFinished.emit()

    assert furniture(window)[-1].shape == RectShape(width=160, depth=80)
    assert page.error.text() == "Depth: enter a length greater than 0, such as 120 or 1.2 m."
    assert page.fields["depth"].text() == "80 cm"
    assert table.id == furniture(window)[-1].id


def test_shortcuts_rotate_nudge_and_lock_but_not_while_typing(window: MainWindow) -> None:
    add_table(window)
    window.view.setFocus()
    start = furniture(window)[-1]

    for key, modifier in ((Qt.Key.Key_R, 0), (Qt.Key.Key_Right, 0), (Qt.Key.Key_Down, 1)):
        QTest.keyClick(
            window.view,
            key,
            Qt.KeyboardModifier.ShiftModifier if modifier else Qt.KeyboardModifier(0),
        )
    window.properties.furniture_page.fields["notes"].setFocus()
    QTest.keyClick(window.properties.furniture_page.fields["notes"], Qt.Key.Key_Up)
    window.view.setFocus()
    QTest.keyClick(window.view, Qt.Key.Key_L)

    moved = furniture(window)[-1]
    assert moved.rotation == 90
    assert (moved.x - start.x, moved.y - start.y) == (1, 10)
    assert moved.locked


def test_group_and_select_all(window: MainWindow) -> None:
    first, second = add_table(window), add_table(window)

    window.select_all_action.trigger()
    window.group_action.trigger()
    editor(window).select({first.id})
    window.commands.select_with_groups(first.id)

    assert editor(window).selection == {first.id, second.id}
    assert len(editor(window).doc.active_layout.groups) == 1


def test_layouts_switch_without_undo_and_keep_their_own_furniture(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = add_table(window)
    first = editor(window).doc.active_layout_id

    window.layout_actions[0].trigger()  # add an empty layout and switch to it
    assert furniture(window) == []
    monkeypatch.setattr(dialogs, "ask_text", lambda *args: "Empty")
    window.layout_actions[1].trigger()
    window.choose_layout(first)

    assert [f.id for f in furniture(window)] == [table.id]
    assert [layout.name for layout in editor(window).doc.layouts] == ["Layout 1", "Empty"]
    assert window.tools.layouts.currentText() == "Layout 1"
    window.undo_action.trigger()  # undoes the rename, not the switch
    assert editor(window).doc.active_layout_id == first
    assert editor(window).doc.layouts[1].name == "Layout 2"


def test_deleting_a_layout_asks_first(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    window.layout_actions[2].trigger()  # duplicate
    answers = iter([False, True])
    monkeypatch.setattr(dialogs, "confirm", lambda *args: next(answers))

    window.layout_actions[3].trigger()
    assert len(editor(window).doc.layouts) == 2
    window.layout_actions[3].trigger()

    assert [layout.name for layout in editor(window).doc.layouts] == ["Layout 1"]


def test_unticked_furniture_is_hidden(window: MainWindow) -> None:
    table = add_table(window)

    window.tools.furniture.item(0).setCheckState(Qt.CheckState.Unchecked)

    assert window.view.hidden == {table.id}
    assert window.view.plan.furniture == []


def test_fit_checks_panel_lists_findings_and_selects_their_items(window: MainWindow) -> None:
    first, second = add_table(window), add_table(window)  # both at the view's centre
    panel = window.findings

    assert panel.summary.text() == "1 collision, 0 warnings"
    editor(window).select(())
    panel.list.itemClicked.emit(panel.list.item(0))

    assert editor(window).selection == {first.id, second.id}
    window.undo_action.trigger()
    assert panel.summary.text() == "Everything fits."


def test_shortcuts_work_without_menu_entries(window: MainWindow) -> None:
    assert [menu.text() for menu in window.menuBar().actions()] == ["&File", "&Help"]
    first = add_table(window)
    add_table(window)
    window.view.setFocus()

    QTest.keyClick(window.view, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(window.view, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
    assert len(editor(window).doc.active_layout.groups) == 1
    editor(window).select({first.id})
    QTest.keyClick(window.view, Qt.Key.Key_Delete)

    assert len(furniture(window)) == 1
    assert first.id not in {f.id for f in furniture(window)}


def test_colour_is_picked_from_the_colour_dialog_and_can_be_reset(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_table(window)
    picker = window.properties.furniture_page.colour
    monkeypatch.setattr(dialogs, "choose_colour", lambda parent, start: "#a0b0c0")

    picker.swatch.click()
    assert furniture(window)[-1].color == "#a0b0c0"
    picker.reset.click()

    assert furniture(window)[-1].color is None
    window.undo_action.trigger()
    assert furniture(window)[-1].color == "#a0b0c0"
    assert picker.colour == "#a0b0c0"


def test_turn_buttons_rotate_either_way_and_update_the_field(window: MainWindow) -> None:
    add_table(window)
    page = window.properties.furniture_page

    page.turn_buttons["anticlockwise"].click()
    assert furniture(window)[-1].rotation == 345
    assert page.fields["rotation"].text() == "345°"
    page.turn_buttons["clockwise"].click()
    page.turn_buttons["clockwise"].click()

    assert furniture(window)[-1].rotation == 15
    assert page.fields["rotation"].text() == "15°"
    page.turn_buttons["clockwise 90"].click()
    page.turn_buttons["anticlockwise 90"].click()
    page.turn_buttons["anticlockwise 90"].click()
    assert page.fields["rotation"].text() == "285°"
    assert page.turn_buttons["clockwise 90"].toolTip() == "Turn 90° clockwise (R)"
    assert page.turn_buttons["anticlockwise 90"].toolTip() == "Turn 90° anticlockwise (Shift+R)"


def test_copy_cut_and_paste_with_the_keyboard(window: MainWindow) -> None:
    table = add_table(window)
    window.view.setFocus()
    ctrl = Qt.KeyboardModifier.ControlModifier

    QTest.keyClick(window.view, Qt.Key.Key_C, ctrl)
    QTest.keyClick(window.view, Qt.Key.Key_V, ctrl)
    QTest.keyClick(window.view, Qt.Key.Key_V, ctrl)
    first, second = furniture(window)[1:]
    assert [(f.name, f.x - table.x, f.y - table.y) for f in (first, second)] == [
        ("Table 2", 50, 50),
        ("Table 3", 100, 100),
    ]
    assert editor(window).selection == {second.id}

    QTest.keyClick(window.view, Qt.Key.Key_X, ctrl)
    assert [f.name for f in furniture(window)] == ["Table", "Table 2"]
    QTest.keyClick(window.view, Qt.Key.Key_V, ctrl)  # back where it was cut from
    pasted = furniture(window)[-1]
    assert (pasted.name, pasted.x, pasted.y) == ("Table 3", second.x, second.y)
