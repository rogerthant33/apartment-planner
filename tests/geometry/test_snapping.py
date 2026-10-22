import pytest

from apartment_planner.geometry.snapping import (
    SnapKind,
    SnapTargets,
    nearest_on_segment,
    room_targets,
    snap,
)
from tests.factories import rect_room

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
