import math
from typing import Literal

import pytest

from apartment_planner.geometry.constants import ELLIPSE_SEGMENTS
from apartment_planner.geometry.openings import (
    door_swing,
    edge,
    edge_dimensions,
    inward_normal,
    nearest_edge,
    opening_at,
    opening_span,
    wall_pieces,
)
from apartment_planner.model import DoorSpec, Opening, Room, Vertex
from tests.factories import rect_room

ROOM = rect_room(0, 0, 400, 300)  # clockwise: top edge runs left to right
# No axis-aligned edge and no corner at the origin, with vertex IDs that don't sort in
# drawing order. The edge from v-c runs to v-a: 400 cm along the unit vector (0.8, 0.6).
SLOPED = Room(
    id="sloped",
    name="Sloped",
    vertices=(
        Vertex(id="v-b", x=40, y=380),
        Vertex(id="v-c", x=100, y=60),
        Vertex(id="v-a", x=420, y=300),
    ),
)


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
    # A quarter of the polygon a circle becomes at the shared resolution.
    n = ELLIPSE_SEGMENTS
    assert swing_area.area == pytest.approx(n / 8 * math.sin(2 * math.pi / n) * 80**2)


@pytest.mark.parametrize(
    ("hinge", "swing", "hinge_at", "tip_at", "open_at"),
    [
        ("start", "in", (230, 157.5), (290, 202.5), (185, 217.5)),
        ("start", "out", (230, 157.5), (290, 202.5), (275, 97.5)),
        ("end", "in", (290, 202.5), (230, 157.5), (245, 262.5)),
        ("end", "out", (290, 202.5), (230, 157.5), (335, 142.5)),
    ],
)
def test_door_leaf_turns_on_its_hinge_to_the_chosen_side_of_a_sloping_wall(
    hinge: Hinge,
    swing: Swing,
    hinge_at: tuple[float, float],
    tip_at: tuple[float, float],
    open_at: tuple[float, float],
) -> None:
    sloped_door = Opening(
        id="d",
        kind="door",
        room_id=SLOPED.id,
        # Built at run time, like an ID read from a file: equal to the vertex's, not
        # the same object.
        edge_start_vertex_id="".join(["v-", "c"]),
        offset=200,
        width=75,  # odd, so half of it isn't whole
        door=DoorSpec(hinge=hinge, swing=swing),
    )

    outline = door_swing(SLOPED, sloped_door).exterior.coords

    # From the hinge, round the arc from the closed leaf (in the doorway) to the open one.
    assert outline[0] == pytest.approx(hinge_at)
    assert outline[1] == pytest.approx(tip_at)
    assert outline[-2] == pytest.approx(open_at)
    assert all(math.dist(p, hinge_at) == pytest.approx(75) for p in outline[1:-1])


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


def test_nearest_edge_takes_the_nearest_of_several_in_reach() -> None:
    other = rect_room(400, 0, 200, 300)

    # In visiting order: ROOM's right wall 4 cm away, its bottom wall 3 cm, then the
    # other room's bottom wall 5 cm and its left wall 4 cm.
    found = nearest_edge([ROOM, other], (396, 297), tolerance=5)

    assert found == (ROOM, ROOM.vertices[2].id, 4)


def test_nearest_edge_reaches_exactly_the_tolerance() -> None:
    found = nearest_edge([ROOM], (200, 5), tolerance=5)

    assert found == (ROOM, ROOM.vertices[0].id, 200)


LEFT = door(0, 100).evolve(id="left")  # spans x 60..140 on the top wall
RIGHT = door(0, 185).evolve(id="right")  # spans x 145..225


@pytest.mark.parametrize("openings", [[LEFT, RIGHT], [RIGHT, LEFT]])
def test_opening_at_picks_the_nearest_span_within_tolerance(openings: list[Opening]) -> None:
    # 3.2 cm from one span's end and 5 cm (the tolerance) from the other's.
    assert opening_at([ROOM], openings, (141, 3), tolerance=5) == "left"
    assert opening_at([ROOM], openings, (144, 3), tolerance=5) == "right"
    # Equally near both: the first listed wins.
    assert opening_at([ROOM], openings, (142.5, 3), tolerance=5) == openings[0].id
    assert opening_at([ROOM], openings, (200, 6), tolerance=5) is None


def test_opening_at_reaches_exactly_the_tolerance() -> None:
    assert opening_at([ROOM], [RIGHT], (141, 3), tolerance=5) == "right"


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
        (0, 60),
        (60, 140),
        (140, 260),
        (260, 340),
        (340, 400),
    ]
    assert wall_pieces(ROOM, openings, ROOM.vertices[2].id) == []  # no opening there


@pytest.mark.parametrize(
    ("openings", "expected"),
    [
        # Flush with the corner: no zero-length wall piece before it.
        ([window(0, 40)], [(0, 80), (80, 400)]),
        # Touching openings stay two; overlapping ones become one.
        (
            [window(0, 140), window(0, 220)],
            [(0, 100), (100, 180), (180, 260), (260, 400)],
        ),
        ([window(0, 140), window(0, 200)], [(0, 100), (100, 240), (240, 400)]),
        # As wide as the wall.
        ([window(0, 200, 400)], [(0, 400)]),
    ],
)
def test_wall_pieces_at_the_edges_of_openings(
    openings: list[Opening], expected: list[tuple[float, float]]
) -> None:
    assert wall_pieces(ROOM, openings, ROOM.vertices[0].id) == expected


def test_edge_dimensions_split_walls_with_openings_and_move_their_length_outside() -> None:
    dims = edge_dimensions(ROOM, [door(0, 100)])  # the top wall: 60 + 80 + 260 cm

    assert dims[:5] == [
        ((200, 0), 400, (0, -1)),  # outside: the room is below the top wall
        ((30, 0), 60, (0, 1)),
        ((100, 0), 80, (0, 1)),
        ((270, 0), 260, (0, 1)),
        ((400, 150), 300, (0, 0)),  # no openings: on the wall line
    ]
    assert [d.length for d in dims[5:]] == [400, 300]
