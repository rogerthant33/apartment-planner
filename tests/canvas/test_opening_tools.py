import pytest
from pytestqt.qtbot import QtBot

from apartment_planner.canvas.tools import Pointer
from apartment_planner.canvas.view import PlanView
from apartment_planner.model import ProjectDoc, RectShape, new_project
from apartment_planner.state.editor import EditorState
from apartment_planner.state.furniture import add_furniture
from apartment_planner.state.openings import add_opening
from apartment_planner.state.placed import add_obstacle
from apartment_planner.state.rooms import add_room
from tests.factories import NOW

XY = tuple[float, float]


def flat() -> ProjectDoc:
    """A 400 by 300 cm room with a door 100 cm along its top wall, a 30 cm column
    at (300, 200) and a chair at (100, 200)."""
    doc, room_id = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    top = doc.apartment.rooms[0].vertices[0].id
    doc, _ = add_opening(doc, "door", room_id, top, 100)
    doc, _ = add_obstacle(doc, RectShape(width=30, depth=30), (300, 200), "Column")
    doc, _ = add_furniture(doc, RectShape(width=40, depth=40), (100, 200), "Chair")
    return doc


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


def lock(view: PlanView) -> None:
    doc = view.state.doc
    view.state.update_untracked(doc.evolve(settings=doc.settings.evolve(apartment_locked=True)))


def test_window_tool_places_on_the_nearest_wall_on_the_grid(
    view: PlanView, messages: list[str]
) -> None:
    view.set_tool("window")

    view.tool.press(at(200, 150))  # the middle of the room, far from any wall
    view.tool.press(at(394, 236))  # 6 cm from the right wall, 236 cm along it

    window = view.state.doc.apartment.openings[-1]
    right = view.state.doc.apartment.rooms[0].vertices[1].id
    assert (window.kind, window.edge_start_vertex_id, window.offset) == ("window", right, 240)
    assert view.state.selection == {window.id}
    assert messages == ["Click on a wall to place the window."]
    view.refresh()
    assert len(view.plan.openings) == 2


def test_dragging_an_opening_moves_it_to_another_wall_in_one_step(view: PlanView) -> None:
    door = view.state.doc.apartment.openings[0]
    bottom = view.state.doc.apartment.rooms[0].vertices[2].id

    drag(view, (90, 1), (150, 100), (152, 297))  # bottom runs from x=400 to x=0

    moved = view.state.doc.apartment.openings[0]
    assert (moved.edge_start_vertex_id, moved.offset) == (bottom, 250)
    assert view.state.selection == {door.id}
    view.state.undo()
    assert view.state.doc.apartment.openings[0] == door


def test_obstacles_move_and_delete_only_while_the_apartment_is_unlocked(view: PlanView) -> None:
    column = view.state.doc.apartment.obstacles[0]

    lock(view)
    drag(view, (300, 200), (350, 250))
    view.set_tool("door")
    view.tool.press(at(100, 2))
    assert view.state.doc.apartment.obstacles == (column,)
    assert len(view.state.doc.apartment.openings) == 1

    view.set_tool("select")
    view.state.update_untracked(
        view.state.doc.evolve(settings=view.state.doc.settings.evolve(apartment_locked=False))
    )
    drag(view, (300, 200), (351, 249), alt=True, snapping=False)
    moved = view.state.doc.apartment.obstacles[0]
    assert (moved.x, moved.y) == (351, 249)
    view.delete_selection()
    assert not view.state.doc.apartment.obstacles


def test_shift_click_on_the_other_kind_starts_a_new_selection(view: PlanView) -> None:
    chair = view.state.doc.active_layout.furniture[0]
    column = view.state.doc.apartment.obstacles[0]

    drag(view, (100, 200))
    assert view.state.selection == {chair.id}
    drag(view, (300, 200), shift=True)

    assert view.state.selection == {column.id}


def test_deleting_a_selected_opening(view: PlanView) -> None:
    drag(view, (100, 0))

    view.delete_selection()

    assert view.state.doc.apartment.openings == ()
    assert len(view.state.doc.apartment.rooms) == 1


def test_a_selected_room_shows_its_walls_split_by_openings(view: PlanView) -> None:
    room_id = view.state.doc.apartment.rooms[0].id

    view.state.select({room_id})
    view.refresh()

    (room_item,) = view.plan.rooms
    assert [label.text for label in room_item.dimension_labels] == [
        "400 cm",
        "60 cm",
        "80 cm",
        "260 cm",
        "300 cm",
        "400 cm",
        "300 cm",
    ]
