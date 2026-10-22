import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from apartment_planner.canvas import style
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


def test_locked_apartment_rooms_are_selected_by_a_click_but_not_moved_or_drawn(
    view: PlanView, messages: list[str]
) -> None:
    (existing,) = with_rooms(view, SQUARE)
    doc = view.state.doc
    view.state.update_untracked(doc.evolve(settings=doc.settings.evolve(apartment_locked=True)))

    drag(view.tool, (100, 100))
    assert view.state.selection == {existing.id}
    view.delete_selection()
    assert messages == ["The apartment is locked. Unlock it to delete rooms, doors or obstacles."]
    shift_click = Pointer((100, 100), cm_per_px=1.0, snapping=True, shift=True)
    view.tool.press(shift_click)
    view.tool.release(shift_click)
    assert view.state.selection == frozenset()  # Shift toggles it off again
    drag(view.tool, (100, 100))
    drag(view.tool, (100, 100), (150, 100))  # a drag is a band, not a move
    assert view.state.selection == frozenset()
    view.set_tool("rect")
    drag(view.tool, (500, 0), (700, 200))

    assert view.state.doc.apartment.rooms == (existing,)


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
    assert view.tool is view.tools["select"]  # a finished room ends the tool

    view.set_tool("polygon")
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
    assert "crosses itself" in messages[-1]
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


NEIGHBOUR = [(600.0, 0.0), (900.0, 0.0), (900.0, 300.0), (600.0, 300.0)]


def test_dragging_a_room_moves_it_once_and_snaps_it_against_another(view: PlanView) -> None:
    first, _ = with_rooms(view, SQUARE, NEIGHBOUR)

    drag(view.tools["select"], (200, 150), (300, 160), (393, 152))  # right wall 7 cm short

    assert corners(room(view.state.doc, first.id))[1] == (600, 0)  # corner to corner
    assert view.state.selection == {first.id}
    view.state.undo()
    assert corners(room(view.state.doc, first.id)) == SQUARE


def test_a_click_with_a_little_jitter_does_not_move_a_room(view: PlanView) -> None:
    (only,) = with_rooms(view, SQUARE)

    drag(view.tools["select"], (200, 150), (203, 150), snapping=False)  # under 4 px

    assert corners(room(view.state.doc, only.id)) == SQUARE


def test_ctrl_click_adds_rooms_and_dragging_moves_them_together(view: PlanView) -> None:
    first, second = with_rooms(view, SQUARE, NEIGHBOUR)
    select = view.tools["select"]

    select.press(Pointer((200, 150), cm_per_px=1.0, snapping=True))
    select.release(Pointer((200, 150), cm_per_px=1.0, snapping=True))
    select.press(Pointer((700, 150), cm_per_px=1.0, snapping=True, ctrl=True))
    assert view.state.selection == {first.id, second.id}
    drag(select, (700, 150), (700, 250), snapping=False)

    assert corners(room(view.state.doc, first.id))[0] == (0, 100)
    assert corners(room(view.state.doc, second.id))[0] == (600, 100)


def test_several_selected_rooms_show_no_corner_handles(view: PlanView) -> None:
    first, second = with_rooms(view, SQUARE, NEIGHBOUR)

    view.state.select({first.id, second.id})
    view.refresh()

    assert [len(item.handles) for item in view.plan.rooms] == [0, 0]
    view.state.select({second.id})
    view.refresh()
    assert [len(item.handles) for item in view.plan.rooms] == [0, 4]


def test_a_read_only_project_selects_rooms_but_does_not_move_them(view: PlanView) -> None:
    (only,) = with_rooms(view, SQUARE)
    view.set_state(view.state, editable=False)

    drag(view.tools["select"], (200, 150))
    assert view.state.selection == {only.id}
    drag(view.tools["select"], (200, 150), (300, 250))  # a band, as in a locked apartment

    assert corners(room(view.state.doc, only.id)) == SQUARE


def test_polygon_finishes_on_double_click_and_right_click_removes_a_corner(view: PlanView) -> None:
    view.set_tool("polygon")
    for point in [(0, 0), (300, 0), (300, 200), (100, 300)]:
        view.tool.press(at(*point))
    view.tool.right_click(at(100, 300))  # takes back (100, 300)
    view.tool.right_click(at(0, 0))  # and (300, 200)

    view.tool.press(at(300, 200))
    view.tool.double_click(at(300, 200))

    (created,) = view.state.doc.apartment.rooms
    assert corners(created) == [(0, 0), (300, 0), (300, 200)]
    assert view.tool is view.tools["select"]


def test_clicking_the_same_corner_twice_adds_it_once(view: PlanView) -> None:
    view.set_tool("polygon")
    for point in [(0, 0), (300, 0), (300, 0.9), (300, 200)]:  # 0.9 cm apart: the same corner
        view.tool.press(at(*point, snapping=False))

    assert view.tool.key(Qt.Key.Key_Return)

    assert corners(view.state.doc.apartment.rooms[0]) == [(0, 0), (300, 0), (300, 200)]


def test_a_double_click_with_too_few_corners_does_nothing(view: PlanView) -> None:
    view.set_tool("polygon")
    view.tool.press(at(0, 0))
    view.tool.press(at(300, 0))

    view.tool.double_click(at(300, 0))

    assert view.state.doc.apartment.rooms == ()
    assert view.tool is view.tools["polygon"]


def test_the_first_corner_is_marked_and_fills_when_a_click_would_close(view: PlanView) -> None:
    view.set_tool("polygon")
    for point in [(0, 0), (300, 0), (300, 200)]:
        view.tool.press(at(*point))

    view.tool.move(at(150, 250))
    marker = view.plan.preview.start_marker
    assert marker is not None and (marker.pos().x(), marker.pos().y()) == (0, 0)
    assert marker.brush().color() == style.colours.handle_fill
    view.tool.move(at(4, 6))  # within 10 px of the first corner

    marker = view.plan.preview.start_marker
    assert marker is not None and marker.brush().color() == style.colours.accent
    assert view.plan.preview.label_texts == ["300 cm", "200 cm", "360.6 cm"]  # closed


def test_measuring_by_two_clicks_and_clearing_it(view: PlanView, messages: list[str]) -> None:
    with_rooms(view, SQUARE)
    view.set_tool("measure")
    free = {"snapping": False}

    drag(view.tool, (10, 10), **free)  # a click: waits for the second point
    view.tool.move(at(13, 10, **free))
    view.tool.press(at(10, 110, **free))
    assert messages[-1] == "Distance: 100 cm"
    view.tool.move(at(10, 200, **free))  # the measurement stays put
    assert view.plan.preview.label_texts == ["100 cm"]
    drag(view.tool, (3, 296), (397, 298))  # a new one, snapped to the room's corners
    assert messages[-1] == "Distance: 400 cm"
    view.tool.key(Qt.Key.Key_Escape)

    assert view.plan.preview.label_texts == []
