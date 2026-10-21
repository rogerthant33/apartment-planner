import pytest
from shapely import unary_union
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from apartment_planner.geometry.constants import EPS
from apartment_planner.geometry.overlap import distance, is_substantial, outside, overlaps
from apartment_planner.geometry.shapes import placed_polygon, room_polygon
from apartment_planner.geometry.transform import local_to_world, rotate
from tests.factories import rect_item, rect_room


def box(x: float, y: float, w: float, d: float, rotation: float = 0) -> Polygon:
    """A w-by-d rectangle whose top-left corner is at (x, y) before rotation about that corner."""
    return placed_polygon(
        rect_item(w, d, *local_to_world((w / 2, d / 2), (x, y), rotation), rotation)
    )


def rooms(*specs: tuple[float, float, float, float]) -> BaseGeometry:
    return unary_union([room_polygon(rect_room(*spec)) for spec in specs])


@pytest.mark.parametrize("angle", [0, 90, 37])
def test_flush_boxes_do_not_overlap(angle: float) -> None:
    # Sharing a rotated edge: floating-point noise must not register.
    a = box(0, 0, 100, 60, angle)
    b = box(*rotate((100, 0), angle), 80, 60, angle)
    assert not overlaps(a, b)


@pytest.mark.parametrize("angle", [0, 90, 37])
def test_overlapping_boxes_overlap(angle: float) -> None:
    a = box(0, 0, 100, 60, angle)
    b = box(*rotate((90, 0), angle), 80, 60, angle)
    assert overlaps(a, b)


@pytest.mark.parametrize(("depth", "expected"), [(0.9 * EPS, False), (1.1 * EPS, True)])
def test_overlap_counts_only_beyond_eps(depth: float, expected: bool) -> None:
    assert overlaps(box(0, 0, 100, 100), box(100 - depth, 0, 100, 100)) is expected


@pytest.mark.parametrize(("side", "expected"), [(0.9 * EPS, False), (1.1 * EPS, True)])
def test_small_square_is_substantial_only_beyond_eps(side: float, expected: bool) -> None:
    # Squares, unlike long strips, also pin down the area shortcut.
    assert is_substantial(box(0, 0, side, side)) is expected


def test_item_flush_in_room_corner_is_not_outside() -> None:
    assert not outside(box(0, 0, 200, 90), rooms((0, 0, 400, 300)))


def test_item_through_wall_is_outside() -> None:
    assert outside(box(350, 50, 100, 100), rooms((0, 0, 400, 300)))


def test_item_poking_out_less_than_eps_is_not_outside() -> None:
    assert not outside(box(300 + 0.9 * EPS, 50, 100, 100), rooms((0, 0, 400, 300)))


def test_item_spanning_two_adjacent_rooms_is_inside_their_union() -> None:
    assert not outside(box(350, 50, 100, 100), rooms((0, 0, 400, 300), (400, 0, 300, 300)))


@pytest.mark.parametrize("angle", [90, 37])
def test_rotated_item_flush_against_rotated_room_wall(angle: float) -> None:
    assert not outside(box(0, 0, 200, 90, angle), box(0, 0, 400, 300, angle))


def test_no_rooms_means_outside() -> None:
    assert outside(box(0, 0, 10, 10), Polygon())


def test_distance_between_rotated_boxes() -> None:
    # A 37°-rotated box moved 25 cm past its twin along their shared +y axis.
    a = box(0, 0, 100, 50, 37)
    b = box(*rotate((0, 75), 37), 100, 50, 37)
    assert distance(a, b) == pytest.approx(25)
