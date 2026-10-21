import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from apartment_planner.canvas.tools import Pointer, Tool
from apartment_planner.canvas.view import PlanView
from apartment_planner.model import ProjectDoc, Room, new_project
from apartment_planner.state.editor import EditorState
from apartment_planner.state.rooms import add_room, room
from tests.factories import NOW

XY = tuple[float, float]


@pytest.fixture
def view(qtbot: QtBot) -> PlanView:
    view = PlanView()
    qtbot.addWidget(view)
    view.set_state(EditorState(new_project("Flat", now=NOW)), editable=True)
    return view


@pytest.fixture
def messages(view: PlanView) -> list[str]:
    """What the view told the user."""
    received: list[str] = []
    view.message.connect(received.append)
    return received


def at(x: float, y: float, *, snapping: bool = True) -> Pointer:
    return Pointer((x, y), cm_per_px=1.0, snapping=snapping)


def drag(tool: Tool, *points: XY, snapping: bool = True) -> None:
    tool.press(at(*points[0], snapping=snapping))
    for point in points[1:]:
        tool.move(at(*point, snapping=snapping))
    tool.release(at(*points[-1], snapping=snapping))


def corners(r: Room) -> list[XY]:
    return [(v.x, v.y) for v in r.vertices]


def with_rooms(view: PlanView, *outlines: list[XY]) -> list[Room]:
    doc: ProjectDoc = view.state.doc
    ids = []
    for outline in outlines:
        doc, room_id = add_room(doc, outline)
        ids.append(room_id)
    view.state.commit(doc)
    return [room(doc, i) for i in ids]


SQUARE = [(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0)]


def test_rectangle_drag_is_snapped_committed_once_and_selected(view: PlanView) -> None:
    view.set_tool("rect")

    drag(view.tool, (3, 4), (150, 77), (398, 302))

    (created,) = view.state.doc.apartment.rooms
    assert corners(created) == SQUARE
    assert view.state.selection == {created.id}
    view.state.undo()
    assert view.state.doc.apartment.rooms == ()
    assert not view.state.can_undo


def test_alt_suspends_snapping(view: PlanView) -> None:
    view.set_tool("rect")

    drag(view.tool, (3, 4), (398, 302), snapping=False)

    assert corners(view.state.doc.apartment.rooms[0])[0] == (3, 4)


def test_a_click_without_a_drag_draws_nothing(view: PlanView, messages: list[str]) -> None:
    view.set_tool("rect")

    drag(view.tool, (100, 100))

    assert view.state.doc.apartment.rooms == ()
    assert messages == []


def test_vertex_drag_snaps_to_another_room_and_commits_on_release(view: PlanView) -> None:
    edited, neighbour = with_rooms(view, SQUARE, [(450, 0), (700, 0), (700, 300), (450, 307)])
    view.state.select({edited.id})
    tool = view.tool

    drag(tool, (400, 300), (430, 305), (447, 303))

    assert corners(room(view.state.doc, edited.id))[2] == (450, 307)  # the neighbour's corner
    assert view.state.selection == {edited.id, edited.vertices[2].id}
    view.state.undo()
    assert room(view.state.doc, edited.id) == edited
    assert room(view.state.doc, neighbour.id) == neighbour


def test_invalid_vertex_drag_previews_in_red_and_reverts_with_a_reason(
    view: PlanView, messages: list[str]
) -> None:
    (edited,) = with_rooms(view, SQUARE)
    view.state.select({edited.id})
    before = view.state.doc

    view.tool.press(at(400, 0))
    view.tool.move(at(200, 400))
    assert view.plan.preview.isVisible()
    assert not view.plan.preview.valid
    view.tool.release(at(200, 400))

    assert view.state.doc == before
    assert not view.plan.preview.isVisible()
    assert messages == [
        "The outline crosses itself. Move a corner so no edges cross. "
        "The corner went back to where it was."
    ]


def test_clicking_selects_the_topmost_room_or_clears_the_selection(view: PlanView) -> None:
    lower, upper = with_rooms(view, SQUARE, [(200, 0), (600, 0), (600, 300), (200, 300)])

    view.tool.press(at(300, 100))
    assert view.state.selection == {upper.id}
    view.tool.press(at(100, 100))
    assert view.state.selection == {lower.id}
    view.tool.press(at(1000, 1000))
    assert view.state.selection == frozenset()


def test_double_click_on_an_edge_inserts_a_selected_vertex(view: PlanView) -> None:
    (edited,) = with_rooms(view, SQUARE)

    view.tool.double_click(at(150, 3))

    updated = room(view.state.doc, edited.id)
    assert corners(updated)[:3] == [(0, 0), (150, 0), (400, 0)]
    assert view.state.selection == {edited.id, updated.vertices[1].id}


def test_locked_apartment_cannot_be_selected_or_drawn(view: PlanView) -> None:
    (existing,) = with_rooms(view, SQUARE)
    doc = view.state.doc
    view.state.update_untracked(doc.evolve(settings=doc.settings.evolve(apartment_locked=True)))

    view.tool.press(at(100, 100))
    view.set_tool("rect")
    drag(view.tool, (500, 0), (700, 200))

    assert view.state.selection == frozenset()
    assert [r.id for r in view.state.doc.apartment.rooms] == [existing.id]


def test_polygon_closes_on_its_first_corner(view: PlanView) -> None:
    view.set_tool("polygon")
    for point in [(0, 0), (300, 0), (300, 200), (100, 300)]:
        view.tool.press(at(*point))
        view.tool.release(at(*point))

    view.tool.press(at(4, 6))  # within 10 px of the first corner

    (created,) = view.state.doc.apartment.rooms
    assert corners(created) == [(0, 0), (300, 0), (300, 200), (100, 300)]


def test_polygon_keys_finish_undo_a_corner_and_cancel(view: PlanView) -> None:
    view.set_tool("polygon")
    for point in [(0, 0), (300, 0), (300, 200), (500, 500)]:
        view.tool.press(at(*point))

    assert view.tool.key(Qt.Key.Key_Backspace)
    assert view.tool.key(Qt.Key.Key_Return)
    assert corners(view.state.doc.apartment.rooms[0]) == [(0, 0), (300, 0), (300, 200)]

    view.tool.press(at(0, 400))
    assert view.tool.key(Qt.Key.Key_Escape)
    assert not view.tool.key(Qt.Key.Key_Return)  # nothing left to finish
    assert len(view.state.doc.apartment.rooms) == 1


def test_crossing_polygon_is_refused_and_kept_for_fixing(
    view: PlanView, messages: list[str]
) -> None:
    view.set_tool("polygon")
    for point in [(0, 0), (300, 300), (300, 0), (0, 300)]:
        view.tool.press(at(*point))

    view.tool.key(Qt.Key.Key_Return)

    assert view.state.doc.apartment.rooms == ()
    assert "crosses itself" in messages[0]
    view.tool.key(Qt.Key.Key_Backspace)
    view.tool.key(Qt.Key.Key_Return)
    assert len(view.state.doc.apartment.rooms) == 1


def test_delete_removes_the_selected_vertex_but_keeps_three(
    view: PlanView, messages: list[str]
) -> None:
    (triangle,) = with_rooms(view, [(0, 0), (300, 0), (0, 300)])
    view.state.select({triangle.id, triangle.vertices[0].id})

    view.delete_selection()

    assert room(view.state.doc, triangle.id) == triangle
    assert messages == ["A room needs at least 3 corners."]
    view.state.select({triangle.id})
    view.delete_selection()
    assert view.state.doc.apartment.rooms == ()
