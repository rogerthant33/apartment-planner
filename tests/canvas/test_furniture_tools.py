import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from apartment_planner.canvas.tools import Pointer, PolygonTool
from apartment_planner.canvas.view import PlanView
from apartment_planner.model import EllipseShape, PolygonShape, ProjectDoc, RectShape, new_project
from apartment_planner.state.editor import EditorState
from apartment_planner.state.furniture import (
    add_furniture,
    furniture_item,
    group_furniture,
    set_locked,
)
from apartment_planner.state.rooms import add_room
from tests.factories import NOW

XY = tuple[float, float]


def flat() -> ProjectDoc:
    """A 400 by 300 cm room, a 200 by 90 sofa at (200, 100) and a table at (200, 230)."""
    doc, _ = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    doc, _ = add_furniture(doc, RectShape(width=200, depth=90), (200, 100), "Sofa")
    doc, _ = add_furniture(doc, EllipseShape(rx=40, ry=40), (200, 230), "Table")
    return doc.evolve(settings=doc.settings.evolve(apartment_locked=True))


@pytest.fixture
def view(qtbot: QtBot) -> PlanView:
    view = PlanView()
    qtbot.addWidget(view)
    view.set_state(EditorState(flat()), editable=True)
    return view


@pytest.fixture
def messages(view: PlanView) -> list[str]:
    received: list[str] = []
    view.message.connect(received.append)
    return received


def at(x: float, y: float, **flags: bool) -> Pointer:
    return Pointer((x, y), cm_per_px=1.0, snapping=flags.pop("snapping", True), **flags)


def drag(view: PlanView, *points: XY, **flags: bool) -> None:
    view.tool.press(at(*points[0], **flags))
    for point in points[1:]:
        view.tool.move(at(*point, **flags))
    view.tool.release(at(*points[-1], **flags))


def ids(view: PlanView) -> tuple[str, str]:
    sofa, table = view.state.doc.active_layout.furniture
    return sofa.id, table.id


def position(view: PlanView, item_id: str) -> XY:
    item = furniture_item(view.state.doc, item_id)
    return (item.x, item.y)


@pytest.mark.parametrize("modifier", ["shift", "ctrl"])
def test_click_selects_and_shift_or_ctrl_click_toggles(view: PlanView, modifier: str) -> None:
    sofa, table = ids(view)

    drag(view, (200, 100))
    assert view.state.selection == {sofa}
    drag(view, (200, 230), **{modifier: True})
    assert view.state.selection == {sofa, table}
    drag(view, (200, 100), **{modifier: True})
    assert view.state.selection == {table}


def test_clicking_a_group_member_selects_the_group(view: PlanView) -> None:
    sofa, table = ids(view)
    view.state.commit(group_furniture(view.state.doc, [sofa, table])[0])

    drag(view, (200, 230))

    assert view.state.selection == {sofa, table}


def test_drag_moves_the_selection_once_and_snaps_flush_to_the_wall(view: PlanView) -> None:
    sofa, _ = ids(view)

    drag(view, (200, 100), (180, 90), (107, 81))  # the sofa's left edge ends 7 cm from x=0

    assert position(view, sofa) == (100, 81)
    view.state.undo()
    assert position(view, sofa) == (200, 100)
    assert not view.state.can_undo


def test_alt_drag_moves_freely(view: PlanView) -> None:
    sofa, _ = ids(view)

    drag(view, (200, 100), (107, 81), alt=True, snapping=False)

    assert position(view, sofa) == (107, 81)


def test_locked_item_is_selected_but_not_moved(view: PlanView, messages: list[str]) -> None:
    sofa, _ = ids(view)
    view.state.commit(set_locked(view.state.doc, [sofa], True))

    drag(view, (200, 100), (250, 150))

    assert position(view, sofa) == (200, 100)
    assert messages == ['"Sofa" is locked. Unlock it (L) to move or resize it.']


def test_rubber_band_selects_what_it_touches(view: PlanView) -> None:
    sofa, table = ids(view)

    drag(view, (10, 290), (180, 250))
    assert view.state.selection == {table}
    drag(view, (390, 10), (300, 60), shift=True)

    assert view.state.selection == {sofa, table}


def test_corner_handle_resizes_with_the_opposite_corner_fixed(view: PlanView) -> None:
    sofa, _ = ids(view)
    drag(view, (200, 100))

    drag(view, (300, 145), (320, 180))  # the bottom-right corner

    item = furniture_item(view.state.doc, sofa)
    assert item.shape == RectShape(width=220, depth=125)
    assert (item.x, item.y) == (210, 117.5)


def test_rotate_handle_snaps_to_15_degrees_unless_alt_is_held(view: PlanView) -> None:
    sofa, _ = ids(view)
    drag(view, (200, 100))
    handle = (200, 100 - 45 - 28)  # above the top edge, 28 px at 1 cm per px

    drag(view, handle, (260, 50))
    assert furniture_item(view.state.doc, sofa).rotation == 45
    drag(view, (235.36, 45), (260, 40), alt=True)  # the handle, now at 45°

    assert furniture_item(view.state.doc, sofa).rotation == pytest.approx(45)


def test_polygon_corner_drags_and_refuses_crossing_outlines(
    view: PlanView, messages: list[str]
) -> None:
    view.set_tool("shape")
    for point in [(20, 20), (100, 20), (100, 60)]:
        view.tool.press(at(*point))
    assert view.plan.preview.label_texts == ["80 cm", "40 cm"]
    view.tool.key(Qt.Key.Key_Return)
    (shape_id,) = view.state.selection
    assert view.tool is view.tools["select"]

    drag(view, (100, 60), (100, 90))
    drag(view, (20, 20), (100, 40))  # onto the line through the other two corners

    shape = furniture_item(view.state.doc, shape_id).shape
    assert isinstance(shape, PolygonShape)
    assert [(p.x, p.y) for p in shape.points] == [(-40, -20), (40, -20), (40, 50)]
    assert messages == [PolygonTool.hint, "The shape has no area."]


def test_hidden_furniture_is_not_drawn_or_selectable(view: PlanView) -> None:
    sofa, table = ids(view)
    view.state.select({sofa})

    view.set_hidden(frozenset({sofa}))
    drag(view, (200, 100))

    assert [item.item_id for item in view.plan.furniture] == [table]
    assert view.state.selection == {view.state.doc.apartment.rooms[0].id}  # the room under it
