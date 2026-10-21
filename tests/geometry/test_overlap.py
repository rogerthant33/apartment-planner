import pytest
from hypothesis import given
from hypothesis import strategies as st
from shapely.geometry import Polygon

from apartment_planner.geometry import (
    EPS,
    InvalidGeometryError,
    distance,
    is_substantial,
    outside,
    overlaps,
    placed_polygon,
    room_polygon,
)
from apartment_planner.geometry.transform import local_to_world
from tests.factories import rect_item, rect_room


def box(x: float, y: float, w: float, d: float, rotation: float = 0) -> Polygon:
    """A w-by-d rectangle whose top-left corner is at (x, y) before rotation about that corner."""
    return placed_polygon(
        rect_item(w, d, *local_to_world((w / 2, d / 2), (x, y), rotation), rotation)
    )


# --- overlaps --------------------------------------------------------------


def test_clearly_overlapping_boxes_overlap() -> None:
    assert overlaps(box(0, 0, 100, 100), box(50, 50, 100, 100))


def test_separate_boxes_do_not_overlap() -> None:
    assert not overlaps(box(0, 0, 100, 100), box(200, 0, 100, 100))


def test_flush_boxes_do_not_overlap() -> None:
    assert not overlaps(box(0, 0, 100, 100), box(100, 0, 100, 100))


def test_corner_touching_boxes_do_not_overlap() -> None:
    assert not overlaps(box(0, 0, 100, 100), box(100, 100, 100, 100))


def test_overlap_thinner_than_eps_is_ignored() -> None:
    assert not overlaps(box(0, 0, 100, 100), box(100 - EPS / 2, 0, 100, 100))


def test_overlap_just_over_eps_counts() -> None:
    assert overlaps(box(0, 0, 100, 100), box(100 - 2 * EPS, 0, 100, 100))


def test_containment_overlaps() -> None:
    assert overlaps(box(0, 0, 100, 100), box(25, 25, 10, 10))


@pytest.mark.parametrize("angle", [0, 90, 37])
def test_rotated_flush_boxes_do_not_overlap(angle: float) -> None:
    # Two boxes sharing a rotated edge: floating-point noise must not register.
    a = box(0, 0, 100, 60, angle)
    b_corner = local_to_world((100, 0), (0, 0), angle)
    b = box(*b_corner, 80, 60, angle)
    assert not overlaps(a, b)


@pytest.mark.parametrize("angle", [0, 90, 37])
def test_rotated_overlapping_boxes_overlap(angle: float) -> None:
    a = box(0, 0, 100, 60, angle)
    b_corner = local_to_world((90, 0), (0, 0), angle)
    b = box(*b_corner, 80, 60, angle)
    assert overlaps(a, b)


@given(
    st.floats(min_value=-300, max_value=300),
    st.floats(min_value=-300, max_value=300),
    st.floats(min_value=0, max_value=360),
)
def test_overlap_is_symmetric(x: float, y: float, angle: float) -> None:
    a = box(0, 0, 120, 80)
    b = box(x, y, 90, 50, angle)
    assert overlaps(a, b) == overlaps(b, a)


def test_invalid_polygon_raises() -> None:
    bowtie = Polygon([(0, 0), (100, 100), (100, 0), (0, 100)])
    with pytest.raises(InvalidGeometryError):
        overlaps(bowtie, box(0, 0, 10, 10))


# --- outside ---------------------------------------------------------------


def test_item_inside_room_is_not_outside() -> None:
    room = room_polygon(rect_room(0, 0, 400, 300))
    assert not outside(box(50, 50, 100, 100), [room])


def test_item_flush_in_room_corner_is_not_outside() -> None:
    room = room_polygon(rect_room(0, 0, 400, 300))
    assert not outside(box(0, 0, 200, 90), [room])


def test_item_through_wall_is_outside() -> None:
    room = room_polygon(rect_room(0, 0, 400, 300))
    assert outside(box(350, 50, 100, 100), [room])


def test_item_poking_out_less_than_eps_is_not_outside() -> None:
    room = room_polygon(rect_room(0, 0, 400, 300))
    assert not outside(box(300 + EPS / 2, 50, 100, 100), [room])


def test_item_spanning_two_adjacent_rooms_is_inside_their_union() -> None:
    rooms = [
        room_polygon(rect_room(0, 0, 400, 300)),
        room_polygon(rect_room(400, 0, 300, 300)),
    ]
    assert not outside(box(350, 50, 100, 100), rooms)


@pytest.mark.parametrize("angle", [90, 37])
def test_rotated_item_flush_against_rotated_room_wall(angle: float) -> None:
    room = box(0, 0, 400, 300, angle)
    item = box(0, 0, 200, 90, angle)
    assert not outside(item, [room])


def test_no_rooms_means_outside() -> None:
    assert outside(box(0, 0, 10, 10), [])


# --- distance and is_substantial --------------------------------------------


def test_distance_between_separate_boxes() -> None:
    assert distance(box(0, 0, 100, 100), box(130, 0, 100, 100)) == pytest.approx(30)


def test_distance_is_zero_when_touching_or_overlapping() -> None:
    assert distance(box(0, 0, 100, 100), box(100, 0, 100, 100)) == 0
    assert distance(box(0, 0, 100, 100), box(50, 0, 100, 100)) == 0


def test_distance_between_rotated_boxes() -> None:
    # A 37°-rotated box moved 25 cm along its own +y axis from a twin.
    a = box(0, 0, 100, 50, 37)
    b = box(*local_to_world((0, 75), (0, 0), 37), 100, 50, 37)
    assert distance(a, b) == pytest.approx(25)


def test_lines_and_empty_regions_are_not_substantial() -> None:
    a, b = box(0, 0, 100, 100), box(100, 0, 100, 100)
    assert not is_substantial(a.intersection(b))
    assert not is_substantial(Polygon())
