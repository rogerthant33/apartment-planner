from typing import Literal

import pytest
from shapely.geometry import LineString

from apartment_planner.geometry.openings import (
    door_swing,
    edge,
    inward_normal,
    nearest_edge,
    opening_at,
    opening_span,
    wall_pieces,
)
from apartment_planner.model import DoorSpec, Opening
from tests.factories import rect_room

ROOM = rect_room(0, 0, 400, 300)  # clockwise: top edge runs left to right


Hinge = Literal["start", "end"]
Swing = Literal["in", "out"]


def door(edge_index: int, offset: float, hinge: Hinge = "start", swing: Swing = "in") -> Opening:
    return Opening(
        id="d",
        kind="door",
        room_id=ROOM.id,
        edge_start_vertex_id=ROOM.vertices[edge_index].id,
        offset=offset,
        width=80,
        door=DoorSpec(hinge=hinge, swing=swing),
    )


def test_inward_normal_points_into_a_clockwise_room() -> None:
    assert inward_normal(*edge(ROOM, ROOM.vertices[0].id)) == pytest.approx((0, 1))
    assert inward_normal(*edge(ROOM, ROOM.vertices[1].id)) == pytest.approx((-1, 0))


def test_span_is_centred_on_the_offset_along_the_edge() -> None:
    right_wall = door(1, 100)  # from (400, 0) down to (400, 300)

    assert opening_span(ROOM, right_wall) == ((400, 60), (400, 140))


@pytest.mark.parametrize(
    ("hinge", "swing", "bounds"),
    [
        ("start", "in", (60, 0, 140, 80)),
        ("end", "in", (60, 0, 140, 80)),
        ("start", "out", (60, -80, 140, 0)),
    ],
)
def test_door_swing_is_a_quarter_circle_on_the_chosen_side(
    hinge: Hinge, swing: Swing, bounds: tuple[float, ...]
) -> None:
    swing_area = door_swing(ROOM, door(0, 100, hinge, swing))

    assert swing_area.bounds == pytest.approx(bounds)
    assert swing_area.area == pytest.approx(3.14159 * 80**2 / 4, rel=0.01)


def test_hinge_side_decides_where_the_open_leaf_lies() -> None:
    at_start = door_swing(ROOM, door(0, 100, "start"))
    at_end = door_swing(ROOM, door(0, 100, "end"))

    assert at_start.buffer(0.5).contains(LineString([(60, 0), (60, 80)]))
    assert at_end.buffer(0.5).contains(LineString([(140, 0), (140, 80)]))
    assert not at_start.buffer(0.5).contains(LineString([(140, 0), (140, 80)]))


def test_windows_do_not_swing() -> None:
    window = door(0, 100).evolve(kind="window", door=None)

    with pytest.raises(ValueError, match="Only doors"):
        door_swing(ROOM, window)


def test_nearest_edge_finds_the_wall_and_the_distance_along_it() -> None:
    other = rect_room(400, 0, 200, 300)

    found = nearest_edge([ROOM, other], (396, 120), tolerance=5)
    assert found is not None
    room, vertex_id, along = found
    assert (room, vertex_id) == (ROOM, ROOM.vertices[1].id)
    assert along == pytest.approx(120)
    assert nearest_edge([ROOM], (200, 150), tolerance=5) is None


def test_opening_at_picks_the_nearest_span_within_tolerance() -> None:
    near, far = door(0, 100).evolve(id="near"), door(0, 300).evolve(id="far")

    assert opening_at([ROOM], [near, far], (130, 4), tolerance=5) == "near"
    assert opening_at([ROOM], [near, far], (200, 4), tolerance=5) is None


def window(edge_index: int, offset: float, width: float = 80) -> Opening:
    return Opening(
        id=f"w{offset}",
        kind="window",
        room_id=ROOM.id,
        edge_start_vertex_id=ROOM.vertices[edge_index].id,
        offset=offset,
        width=width,
    )


def test_wall_pieces_split_an_edge_around_its_openings_in_order() -> None:
    top = ROOM.vertices[0].id
    openings = [window(0, 300), door(0, 100), window(1, 150)]  # the last is on another edge

    assert wall_pieces(ROOM, openings, top) == [
        (0, 60, False),
        (60, 140, True),
        (140, 260, False),
        (260, 340, True),
        (340, 400, False),
    ]
    assert wall_pieces(ROOM, openings, ROOM.vertices[2].id) == []  # no opening there


@pytest.mark.parametrize(
    ("openings", "expected"),
    [
        # Flush with the corner: no zero-length wall piece before it.
        ([window(0, 40)], [(0, 80, True), (80, 400, False)]),
        # Touching openings stay two; overlapping ones become one.
        (
            [window(0, 140), window(0, 220)],
            [(0, 100, False), (100, 180, True), (180, 260, True), (260, 400, False)],
        ),
        ([window(0, 140), window(0, 200)], [(0, 100, False), (100, 240, True), (240, 400, False)]),
        # As wide as the wall.
        ([window(0, 200, 400)], [(0, 400, True)]),
    ],
)
def test_wall_pieces_at_the_edges_of_openings(
    openings: list[Opening], expected: list[tuple[float, float, bool]]
) -> None:
    assert wall_pieces(ROOM, openings, ROOM.vertices[0].id) == expected
