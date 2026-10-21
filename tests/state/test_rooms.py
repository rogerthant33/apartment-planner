import math

import pytest

from apartment_planner.model import (
    Apartment,
    Opening,
    ProjectDoc,
    Room,
    Vertex,
    new_id,
    new_project,
)
from apartment_planner.state.rooms import (
    EditError,
    add_room,
    delete_room,
    delete_selection,
    delete_vertex,
    duplicate_room,
    insert_vertex,
    move_vertex,
    outline_problem,
    rename_room,
    room,
    selected_room,
    set_edge_length,
    with_default_lock,
)
from tests.factories import NOW, points, rect_item

# Clockwise on screen: top-left, top-right, bottom-right, bottom-left.
SQUARE = [(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0)]


def corners(r: Room) -> list[tuple[float, float]]:
    return [(v.x, v.y) for v in r.vertices]


def with_room(outline: list[tuple[float, float]] = SQUARE) -> tuple[ProjectDoc, Room]:
    doc, room_id = add_room(new_project("Flat", now=NOW), outline)
    return doc, room(doc, room_id)


def with_window(doc: ProjectDoc, r: Room, edge: int, offset: float, width: float) -> ProjectDoc:
    window = Opening(
        id=new_id(),
        kind="window",
        room_id=r.id,
        edge_start_vertex_id=r.vertices[edge].id,
        offset=offset,
        width=width,
    )
    return doc.evolve(apartment=doc.apartment.evolve(openings=(window,)))


def only_opening(doc: ProjectDoc) -> Opening:
    (opening,) = doc.apartment.openings
    return opening


def test_outline_problems_name_the_reason() -> None:
    assert outline_problem(points(*SQUARE)) is None
    assert "inside out" in (outline_problem(points(*reversed(SQUARE))) or "")
    assert "crosses itself" in (
        outline_problem(points((0, 0), (100, 100), (100, 0), (0, 100))) or ""
    )


def test_new_rooms_run_clockwise_and_get_numbered_names() -> None:
    doc, first = with_room(list(reversed(SQUARE)))
    doc, second_id = add_room(doc, SQUARE)

    assert corners(first) == SQUARE
    assert (first.name, room(doc, second_id).name) == ("Room 1", "Room 2")


def test_even_a_tiny_counter_clockwise_room_is_turned_around() -> None:
    doc, room_id = add_room(new_project("Flat"), [(0, 0), (0, 1.5), (1.5, 0)])  # 1.125 cm²

    assert corners(room(doc, room_id)) == [(1.5, 0), (0, 1.5), (0, 0)]


def test_invalid_new_room_is_refused() -> None:
    with pytest.raises(EditError, match="no area"):
        add_room(new_project("Flat"), [(0, 0), (100, 0), (200, 0)])


def test_rename_trims_and_refuses_empty_names() -> None:
    doc, r = with_room()

    assert room(rename_room(doc, r.id, "  Kitchen "), r.id).name == "Kitchen"
    with pytest.raises(EditError, match="Enter a name"):
        rename_room(doc, r.id, "   ")


def test_delete_room_removes_its_openings_and_unassigns_furniture() -> None:
    doc, r = with_room()
    doc, other_id = add_room(doc, [(400, 0), (600, 0), (600, 300), (400, 300)])
    doc = with_window(doc, r, edge=0, offset=100, width=80)
    sofa = rect_item(200, 90).evolve(room_id=r.id)
    lamp = rect_item(30, 30).evolve(room_id=other_id)
    doc = doc.evolve(layouts=(doc.layouts[0].evolve(furniture=(sofa, lamp)),))

    doc = delete_room(doc, r.id)

    assert [x.id for x in doc.apartment.rooms] == [other_id]
    assert doc.apartment.openings == ()
    assert [f.room_id for f in doc.layouts[0].furniture] == [None, other_id]


def test_duplicate_room_copies_openings_with_new_ids() -> None:
    doc, r = with_room()
    doc = with_window(doc, r, edge=1, offset=100, width=80)

    doc, copy_id = duplicate_room(doc, r.id, (50, 25))

    copy = room(doc, copy_id)
    original_window, copied_window = doc.apartment.openings
    assert copy.name == "Room 1 copy"
    assert corners(copy) == [(50, 25), (450, 25), (450, 325), (50, 325)]
    assert not {v.id for v in copy.vertices} & {v.id for v in r.vertices}
    assert copied_window.room_id == copy_id
    assert copied_window.edge_start_vertex_id == copy.vertices[1].id
    assert copied_window.id != original_window.id


def test_move_vertex_refuses_a_crossing_outline() -> None:
    doc, r = with_room()

    with pytest.raises(EditError, match="crosses itself"):
        move_vertex(doc, r.id, r.vertices[1].id, (200, 400))


def test_moving_a_corner_keeps_openings_on_the_shorter_edge() -> None:
    doc, r = with_room()
    doc = with_window(doc, r, edge=0, offset=300, width=81)

    doc = move_vertex(doc, r.id, r.vertices[1].id, (200, 0))

    assert only_opening(doc).offset == 159.5  # 200 cm edge minus half the window


def test_opening_hanging_over_an_edge_start_is_pulled_onto_it() -> None:
    doc, r = with_room()
    doc = with_window(doc, r, edge=0, offset=10, width=80)

    doc = move_vertex(doc, r.id, r.vertices[2].id, (400, 320))

    assert only_opening(doc).offset == 40


def test_edge_length_moves_the_end_vertex_along_the_edge() -> None:
    # A 300-400-500 triangle; its last edge runs diagonally from (300, 400) to (0, 0).
    doc, r = with_room([(0, 0), (300, 0), (300, 400)])

    doc = set_edge_length(doc, r.id, r.vertices[2].id, 250)

    assert corners(room(doc, r.id)) == pytest.approx([(150, 200), (300, 0), (300, 400)])


@pytest.mark.parametrize(
    ("length", "reason"), [(0, "greater than 0"), (-5, "greater than 0"), (0.5, "at least 1 cm")]
)
def test_edge_length_must_be_valid(length: float, reason: str) -> None:
    doc, r = with_room()

    with pytest.raises(EditError, match=reason):
        set_edge_length(doc, r.id, r.vertices[0].id, length)


def test_insert_vertex_splits_the_edge_and_carries_openings_past_the_split() -> None:
    doc, r = with_room()
    doc = with_window(doc, r, edge=0, offset=300, width=80)

    doc, vertex_id = insert_vertex(doc, r.id, r.vertices[0].id, (150, 30))

    assert corners(room(doc, r.id))[:3] == [(0, 0), (150, 0), (400, 0)]
    assert (only_opening(doc).edge_start_vertex_id, only_opening(doc).offset) == (vertex_id, 150)


@pytest.mark.parametrize(
    ("offset", "kept"),
    [(100, 100), (250, 210)],  # before the split; exactly at it (clamped)
)
def test_insert_vertex_keeps_openings_up_to_the_split(offset: float, kept: float) -> None:
    doc, r = with_room()
    doc = with_window(doc, r, edge=0, offset=offset, width=80)

    doc, _ = insert_vertex(doc, r.id, r.vertices[0].id, (250, 0))

    assert only_opening(doc).edge_start_vertex_id == r.vertices[0].id
    assert only_opening(doc).offset == kept


@pytest.mark.parametrize("point", [(0.5, 0), (450, 0)])  # near the start; past the end
def test_insert_vertex_too_close_to_a_corner_is_refused(point: tuple[float, float]) -> None:
    doc, r = with_room()

    with pytest.raises(EditError, match="at least 1 cm"):
        insert_vertex(doc, r.id, r.vertices[0].id, point)


def test_delete_vertex_moves_its_openings_onto_the_merged_edge() -> None:
    doc, r = with_room([(0, 0), (200, 0), (400, 0), (400, 300), (0, 300)])
    doc = with_window(doc, r, edge=1, offset=50, width=40)  # centred at (250, 0)

    doc = delete_vertex(doc, r.id, r.vertices[1].id)

    assert len(room(doc, r.id).vertices) == 4
    assert (only_opening(doc).edge_start_vertex_id, only_opening(doc).offset) == (
        r.vertices[0].id,
        250,
    )


def test_delete_vertex_keeps_at_least_three() -> None:
    doc, r = with_room([(0, 0), (100, 0), (0, 100)])

    with pytest.raises(EditError, match="at least 3 corners"):
        delete_vertex(doc, r.id, r.vertices[0].id)


def test_opening_wider_than_its_shortened_edge_is_centred() -> None:
    doc, r = with_room()
    doc = with_window(doc, r, edge=0, offset=200, width=120)

    doc = move_vertex(doc, r.id, r.vertices[1].id, (100, 0))

    assert only_opening(doc).offset == 50


def test_projects_with_rooms_open_locked() -> None:
    empty = new_project("Flat", now=NOW)
    doc, _ = with_room()

    assert not with_default_lock(empty).settings.apartment_locked
    assert with_default_lock(doc).settings.apartment_locked


def test_delete_selection_prefers_the_selected_vertex() -> None:
    doc, r = with_room([(0, 0), (200, 0), (400, 0), (400, 300), (0, 300)])

    after_vertex = delete_selection(doc, frozenset({r.id, r.vertices[1].id}))
    after_room = delete_selection(doc, frozenset({r.id}))

    assert len(room(after_vertex, r.id).vertices) == 4
    assert after_room.apartment.rooms == ()
    assert selected_room(doc, frozenset({r.vertices[2].id})) == r
    assert selected_room(doc, frozenset()) is None


@pytest.fixture
def three_rooms() -> ProjectDoc:
    """Rooms "room-a", "room-b" and "room-c" side by side, with fixed IDs that sort
    before and after room b's. Each has a window on its first edge; room b has
    another on its last edge (from b3 to b0)."""
    rooms = tuple(
        Room(
            id=f"room-{name}",
            name=name,
            vertices=tuple(
                Vertex(id=f"{name}{i}", x=x + 500 * n, y=y) for i, (x, y) in enumerate(SQUARE)
            ),
        )
        for n, name in enumerate("abc")
    )
    windows = [(r.id, r.vertices[0].id) for r in rooms] + [("room-b", "b3")]
    openings = tuple(
        Opening(
            id=f"window-{vertex_id}",
            kind="window",
            room_id=room_id,
            edge_start_vertex_id=vertex_id,
            offset=100,
            width=80,
        )
        for room_id, vertex_id in windows
    )
    return new_project("Flat", now=NOW).evolve(apartment=Apartment(rooms=rooms, openings=openings))


ROOM_B = "".join(["room-", "b"])  # equal to room b's ID, but not the same string object


def test_editing_a_room_leaves_the_others_alone(three_rooms: ProjectDoc) -> None:
    doc = move_vertex(rename_room(three_rooms, ROOM_B, "Hall"), ROOM_B, "b2", (900, 350))

    a, b, c = doc.apartment.rooms
    assert (a, c) == (three_rooms.apartment.rooms[0], three_rooms.apartment.rooms[2])
    assert b.name == "Hall"
    assert corners(b)[2] == (900, 350)


def test_deleting_a_room_keeps_the_others_and_their_openings(three_rooms: ProjectDoc) -> None:
    doc = delete_room(three_rooms, ROOM_B)

    assert [r.id for r in doc.apartment.rooms] == ["room-a", "room-c"]
    assert [o.room_id for o in doc.apartment.openings] == ["room-a", "room-c"]


def test_duplicating_a_room_copies_only_its_openings(three_rooms: ProjectDoc) -> None:
    doc, copy_id = duplicate_room(three_rooms, ROOM_B, (0, 400))

    copies = doc.apartment.openings[len(three_rooms.apartment.openings) :]
    assert [o.room_id for o in copies] == [copy_id, copy_id]


def test_splitting_or_merging_an_edge_leaves_other_edges_openings_alone(
    three_rooms: ProjectDoc,
) -> None:
    split, _ = insert_vertex(three_rooms, ROOM_B, "b1", (900, 50))
    merged = delete_vertex(three_rooms, ROOM_B, "b1")

    assert corners(split.apartment.rooms[1])[1:3] == [(900, 0), (900, 50)]
    assert split.apartment.openings == three_rooms.apartment.openings
    assert merged.apartment.openings == three_rooms.apartment.openings


def test_insert_vertex_lands_on_a_sloping_edge() -> None:
    doc, r = with_room([(0, 50), (400, 250), (400, 350), (0, 350)])

    doc, _ = insert_vertex(doc, r.id, r.vertices[0].id, (300, 150))

    assert corners(room(doc, r.id))[1] == pytest.approx((280, 190))


def test_delete_vertex_keeps_openings_in_place_on_a_sloping_wall() -> None:
    doc, r = with_room([(0, 300), (0, 0), (200, 100), (400, 200), (400, 300)])
    half = math.hypot(200, 100) / 2
    doc = with_window(doc, r, edge=2, offset=half, width=40)  # centred at (300, 150)

    doc = delete_vertex(doc, r.id, r.vertices[2].id)

    assert only_opening(doc).offset == pytest.approx(0.75 * math.hypot(400, 200))
