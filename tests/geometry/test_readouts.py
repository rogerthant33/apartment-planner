import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from shapely.geometry import Polygon

from apartment_planner.geometry.overlap import outside
from apartment_planner.geometry.readouts import SIDES, Segment, gap_between, wall_gaps
from apartment_planner.geometry.shapes import placed_polygon, room_polygon
from apartment_planner.geometry.transform import rotate
from apartment_planner.model import Room, Vertex
from tests.factories import rect_item, rect_room

ROOM = rect_room(0, 0, 400, 300)


def length(segment: Segment | None) -> float:
    assert segment is not None
    return math.dist(*segment)


def test_gaps_run_from_each_side_to_the_wall_it_faces() -> None:
    desk = rect_item(100, 50, x=100, y=150)  # spans x 50..150, y 125..175

    gaps = wall_gaps(desk, [ROOM])

    assert {side: length(gap) for side, gap in gaps.items()} == {
        "left": 50,
        "right": 250,
        "back": 125,
        "front": 125,
    }
    assert gaps["left"] == ((50, 125), (0, 125))


def test_flush_side_reads_zero_and_the_opposite_side_crosses_the_room() -> None:
    bed = rect_item(100, 50, x=50, y=25)  # in the top-left corner

    gaps = wall_gaps(bed, [ROOM])

    assert (length(gaps["left"]), length(gaps["back"])) == (0, 0)
    assert (length(gaps["right"]), length(gaps["front"])) == (300, 250)


def test_sides_turn_with_the_item() -> None:
    desk = rect_item(100, 50, x=100, y=150, rotation=90)  # its left now faces the top wall

    gaps = wall_gaps(desk, [ROOM])

    assert (length(gaps["left"]), length(gaps["front"])) == (100, 75)


def test_a_wall_corner_in_the_path_stops_the_slide() -> None:
    # The right wall has a V-shaped notch whose tip points left, at (300, 150).
    corners = [(0, 0), (400, 0), (400, 100), (300, 150), (400, 200), (400, 300), (0, 300)]
    notched = Room(
        id="r",
        name="R",
        vertices=tuple(Vertex(id=f"v{i}", x=x, y=y) for i, (x, y) in enumerate(corners)),
    )

    gaps = wall_gaps(rect_item(100, 100, x=100, y=150), [notched])

    assert gaps["right"] == ((150, 150), (300, 150))


def test_no_rooms_means_no_walls() -> None:
    assert set(wall_gaps(rect_item(10, 10), []).values()) == {None}


@given(
    x=st.floats(40, 360),
    y=st.floats(40, 260),
    rotation=st.floats(0, 360),
    side=st.sampled_from(list(SIDES)),
)
def test_sliding_by_the_gap_reaches_the_wall_but_not_beyond(
    x: float, y: float, rotation: float, side: str
) -> None:
    desk = rect_item(40, 20, x=x, y=y, rotation=rotation)
    gap = length(wall_gaps(desk, [ROOM])[side])  # type: ignore[index]
    dx, dy = rotate(SIDES[side], rotation)  # type: ignore[index]
    floor = room_polygon(ROOM)

    def slid(by: float) -> Polygon:
        return placed_polygon(desk.evolve(x=x + dx * by, y=y + dy * by))

    assert not outside(slid(gap), floor)
    assert not floor.covers(slid(gap + 0.5))  # past the wall, if only by a sliver


@pytest.mark.parametrize(("x", "expected"), [(250, 100), (150, 0)])
def test_gap_between_two_items(x: float, expected: float) -> None:
    gap = gap_between(rect_item(100, 100, x=50, y=50), rect_item(100, 100, x=x, y=50))

    assert length(gap) == expected
