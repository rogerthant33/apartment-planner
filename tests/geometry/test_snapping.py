import pytest

from apartment_planner.geometry.snapping import (
    SnapKind,
    SnapTargets,
    measure_targets,
    nearest_on_segment,
    placed_targets,
    room_targets,
    snap,
    snap_move,
    snap_room_move,
)
from tests.factories import rect_item, rect_room

# Two corners on one wall, and a second wall 10 cm below it.
TARGETS = SnapTargets(
    vertices=((100, 200), (300, 200)),
    edges=(((0, 200), (300, 200)), ((0, 210), (300, 210))),
)


@pytest.mark.parametrize(
    ("point", "kind", "snapped"),
    [
        ((103, 203), SnapKind.VERTEX, (100, 200)),  # beats the nearer wall
        ((103, 204), SnapKind.VERTEX, (100, 200)),  # exactly at the tolerance
        ((104, 204), SnapKind.EDGE, (104, 200)),  # just outside it
        ((150, 195), SnapKind.EDGE, (150, 200)),  # exactly at the tolerance
        ((150, 205.5), SnapKind.EDGE, (150, 210)),  # the nearer of two walls
        ((150, 194), SnapKind.GRID, (150, 190)),
        ((-14, 26), SnapKind.GRID, (-10, 30)),
    ],
)
def test_snaps_to_vertices_then_edges_then_the_grid(
    point: tuple[float, float], kind: SnapKind, snapped: tuple[float, float]
) -> None:
    result = snap(point, TARGETS, grid=10, tolerance=5)

    assert result.kind == kind
    assert result.point == pytest.approx(snapped)


def test_without_a_grid_far_points_stay_put() -> None:
    result = snap((150, 194), TARGETS, grid=None, tolerance=5)

    assert (result.kind, result.point) == (SnapKind.NONE, (150, 194))


def test_room_targets_skip_the_room_being_edited() -> None:
    # Fixed IDs that sort before and after the edited room's.
    before, edited, after = (
        rect_room(x, 0, 100, 100).evolve(id=f"room-{name}")
        for x, name in [(0, "a"), (100, "b"), (200, "c")]
    )

    targets = room_targets([before, edited, after], exclude="".join(["room-", "b"]))

    assert targets.vertices == (
        *((0, 0), (100, 0), (100, 100), (0, 100)),
        *((200, 0), (300, 0), (300, 100), (200, 100)),
    )
    assert targets.edges[3] == ((0, 100), (0, 0))


@pytest.mark.parametrize(
    ("point", "expected"),
    [((60, 40), (60, 20)), ((-30, 25), (10, 20)), ((140, 15), (110, 20)), ((60, 60), (60, 20))],
)
def test_nearest_on_segment_stays_within_the_segment(
    point: tuple[float, float], expected: tuple[float, float]
) -> None:
    assert nearest_on_segment(point, (10, 20), (110, 20)) == pytest.approx(expected)


def test_nearest_on_a_sloping_segment() -> None:
    assert nearest_on_segment((30, 50), (10, 10), (50, 50)) == pytest.approx((40, 40))


def test_nearest_on_a_zero_length_segment_is_its_point() -> None:
    assert nearest_on_segment((5, 5), (1, 1), (1, 1)) == (1, 1)


# A room's left and top walls, and a sofa 10 cm from the left one and 2 cm from the
# top one, with its origin off the grid.
WALL = ((3.0, 0.0), (3.0, 400.0))
TOP_WALL = ((0.0, 100.0), (400.0, 100.0))
SOFA_CORNERS = [(13.0, 102.0), (213.0, 102.0), (213.0, 192.0), (13.0, 192.0)]
SOFA_ORIGIN = (113.0, 147.0)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        ((-6, 3), (-10, 3)),  # a corner 4 cm from the wall: flush against it
        ((-5, 3), (-10, 3)),  # exactly at the tolerance
        ((-4, -3), (-3, -7)),  # just outside it: the origin lands on the grid
    ],
)
def test_moves_snap_flush_to_walls_before_the_grid(
    delta: tuple[float, float], expected: tuple[float, float]
) -> None:
    result = snap_move(SOFA_CORNERS, SOFA_ORIGIN, delta, [WALL], grid=10, tolerance=5)

    assert result == pytest.approx(expected)


def test_moves_snap_to_the_nearest_edge_and_stay_free_without_a_grid() -> None:
    near = ((219.0, 0.0), (219.0, 400.0))  # 7 cm from the moved sofa; the wall is 9 cm away

    assert snap_move(SOFA_CORNERS, SOFA_ORIGIN, (-1, 0), [WALL, near], grid=None, tolerance=10) == (
        pytest.approx((6, 0))
    )
    assert snap_move(SOFA_CORNERS, SOFA_ORIGIN, (40, 7), [WALL], grid=None, tolerance=5) == (40, 7)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        ((-7, 2), (-10, -2)),  # 3 cm from the left wall, 4 cm from the top one
        ((-6, 1), (-10, -2)),  # 4 cm from the left wall, 3 cm from the top one
        ((-7, 1), (-10, -2)),  # 3 cm from both
        ((-7, 3), (-10, -2)),  # the top wall 5 cm away: just in reach for the slide
        ((-7, 3.1), (-10, 3.1)),  # 5.1 cm: out of reach, so only flush to the left wall
    ],
)
def test_moves_into_a_corner_snap_flush_to_both_walls(
    delta: tuple[float, float], expected: tuple[float, float]
) -> None:
    result = snap_move(SOFA_CORNERS, SOFA_ORIGIN, delta, [TOP_WALL, WALL], grid=None, tolerance=5)

    assert result == pytest.approx(expected)


def test_placed_targets_follow_the_rotated_footprint() -> None:
    sofa = rect_item(200, 90, x=100, y=100, rotation=90)

    targets = placed_targets([sofa])
    (start, end), *_ = targets.edges
    assert (*start, *end) == pytest.approx((145, 0, 145, 200))
    assert targets.vertices[2] == pytest.approx((55, 200))


NEIGHBOUR = room_targets([rect_room(400, 0, 300, 300)])  # x 400..700, y 0..300
MOVING = [(0.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0)]


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        ((195, 3), (200, 0)),  # corner to corner beats flush along the edge
        ((195, 50), (200, 50)),  # flush against the neighbour's left wall
        ((189.9, 50), (190, 50)),  # just out of reach (10 cm): to the grid instead
        ((-33, 47), (-30, 50)),
    ],
)
def test_room_moves_snap_to_corners_then_walls_then_the_grid(
    delta: tuple[float, float], expected: tuple[float, float]
) -> None:
    moved = snap_room_move(MOVING, delta, NEIGHBOUR, grid=10, tolerance=10)

    assert moved == pytest.approx(expected)


def test_a_corner_slides_along_a_sloping_wall_into_the_corner_it_makes() -> None:
    sloping = ((0.0, 0.0), (400.0, 300.0))  # 37 degrees down from the top-left corner
    left = ((0.0, 0.0), (0.0, 400.0))
    box = [(4.0, 10.0), (60.0, 52.0), (40.0, 80.0), (4.0, 80.0)]  # one corner 4 cm off each

    dx, dy = snap_move(box, (30.0, 50.0), (0, 0), [left, sloping], grid=None, tolerance=10)

    corner = (box[0][0] + dx, box[0][1] + dy)
    assert corner == pytest.approx((0, 0), abs=1e-9)


def test_a_degenerate_edge_is_snapped_to_as_a_point_with_no_slide() -> None:
    point = ((10.0, 100.0), (10.0, 100.0))  # a zero-length edge, as a doubled corner gives

    shift = snap_move(SOFA_CORNERS, SOFA_ORIGIN, (0, 0), [point], grid=None, tolerance=5)

    assert shift == pytest.approx((-3, -2))  # the sofa's corner (13, 102) onto the point


def test_measurements_snap_to_rooms_and_furniture_alike() -> None:
    table = rect_item(40, 40, x=500, y=500)

    targets = measure_targets([rect_room(0, 0, 100, 100)], [table])

    assert targets.vertices[3:5] == pytest.approx([(0, 100), (480, 480)])
    assert len(targets.edges) == 8
