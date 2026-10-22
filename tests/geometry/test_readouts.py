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
from tests.factories import item, polygon_shape, rect_item, rect_room

ROOM = rect_room(0, 0, 400, 300)
# Its right wall, from (0, 0) to (0, 256), is a power of two long, which keeps the ray
# arithmetic exact for the tolerance tests.
LEFT_OF_ORIGIN = rect_room(-400, 0, 400, 256)


def length(segment: Segment | None) -> float:
    assert segment is not None
    return math.dist(*segment)


def room(*corners: tuple[float, float]) -> Room:
    return Room(
        id="r",
        name="R",
        vertices=tuple(Vertex(id=f"v{i}", x=x, y=y) for i, (x, y) in enumerate(corners)),
    )


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
    assert gaps["back"] == ((50, 125), (50, 0))


def test_flush_side_reads_zero_and_the_opposite_side_crosses_the_room() -> None:
    bed = rect_item(100, 50, x=50, y=25)  # in the top-left corner

    gaps = wall_gaps(bed, [ROOM])

    assert (length(gaps["left"]), length(gaps["back"])) == (0, 0)
    assert (length(gaps["right"]), length(gaps["front"])) == (300, 250)


def test_sides_turn_with_the_item() -> None:
    desk = rect_item(100, 50, x=100, y=150, rotation=90)  # its left now faces the top wall

    gaps = wall_gaps(desk, [ROOM])

    assert (length(gaps["left"]), length(gaps["front"])) == (100, 75)


@pytest.mark.parametrize(
    ("notched", "side", "expected"),
    [
        # The right wall has a V-shaped notch whose tip points left, at (300, 150).
        (
            room((0, 0), (400, 0), (400, 100), (300, 150), (400, 200), (400, 300), (0, 300)),
            "right",
            ((150, 150), (300, 150)),
        ),
        # The bottom wall has one whose tip points up, at (100, 250).
        (
            room((0, 0), (400, 0), (400, 300), (150, 300), (100, 250), (50, 300), (0, 300)),
            "front",
            ((100, 200), (100, 250)),
        ),
    ],
)
def test_a_wall_corner_in_the_path_stops_the_slide(
    notched: Room, side: str, expected: Segment
) -> None:
    gaps = wall_gaps(rect_item(100, 100, x=100, y=150), [notched])  # x 50..150, y 100..200

    assert gaps[side] == expected  # type: ignore[index]


def test_a_corner_resting_on_a_sloping_wall_blocks_only_the_way_into_it() -> None:
    sloped = room((0, 0), (400, 0), (400, 300), (0, 300.5))  # the bottom wall drops 0.5 cm
    shelf = rect_item(100, 50, x=150, y=275.25)  # its bottom-right corner is on that wall

    gaps = wall_gaps(shelf, [sloped])

    assert (length(gaps["left"]), length(gaps["right"])) == (100, 0)


def test_a_wall_just_behind_the_item_doesnt_stop_it() -> None:
    hall = rect_room(-200, 0, 200, 300)  # its right wall faces right, 0.5 cm behind the desk
    desk = rect_item(100, 50, x=50.5, y=150)  # x 0.5..100.5

    assert length(wall_gaps(desk, [hall, ROOM])["right"]) == 299.5


START = 256 * -1e-9  # a ray along +x at this y meets the right wall's line 1e-9 before its start
END = 256 * (1 + 1e-9)  # ... and at this y, 1e-9 past its end


@pytest.mark.parametrize(
    ("outline", "expected"),
    [
        # A corner 1e-9 past the wall it moves into is flush, not 1e-9 into the wall.
        ([(-100, 100), (1e-9, 100), (1e-9, 150), (-100, 150)], 0),
        # Wedges whose tip, their only rightmost corner, is 1e-9 beyond a wall end.
        ([(-200, START), (-100, START), (-150, START + 50), (-200, START + 50)], 100),
        ([(-200, END - 50), (-150, END - 50), (-100, END), (-200, END)], 100),
    ],
)
def test_rays_within_the_float_tolerance_of_a_wall_still_hit_it(
    outline: list[tuple[float, float]], expected: float
) -> None:
    gaps = wall_gaps(item(polygon_shape(*outline)), [LEFT_OF_ORIGIN])

    assert length(gaps["right"]) == expected


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


def test_a_wall_shared_with_a_neighbouring_room_does_not_stop_a_slide_away_from_it() -> None:
    neighbour, room = rect_room(-200, 0, 200, 300), rect_room(0, 0, 400, 300)
    desk = rect_item(100, 50, x=50, y=150)  # flush against the shared wall at x=0

    gaps = wall_gaps(desk, [neighbour, room])

    assert length(gaps["right"]) == 300
    assert length(gaps["left"]) == 0
