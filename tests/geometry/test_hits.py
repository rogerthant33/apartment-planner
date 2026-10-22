import pytest

from apartment_planner.geometry.hits import (
    edge_at,
    nearest_within,
    placed_at,
    placed_in_rect,
    rect_outline,
    room_at,
    shape_corners,
    vertex_at,
)
from tests.factories import item, polygon_shape, rect_item, rect_room

ROOM = rect_room(0, 0, 400, 300)


@pytest.mark.parametrize(("point", "expected"), [((403, 4), 1), ((404, 4), None), ((2, 298), 3)])
def test_vertex_at_finds_the_nearest_corner_within_tolerance(
    point: tuple[float, float], expected: int | None
) -> None:
    vertex_id = None if expected is None else ROOM.vertices[expected].id

    assert vertex_at(ROOM, point, tolerance=5) == vertex_id


@pytest.mark.parametrize(
    ("point", "expected"), [((200, 5), 0), ((396, 150), 1), ((200, 150), None)]
)
def test_edge_at_names_the_nearest_edge_by_its_start_vertex(
    point: tuple[float, float], expected: int | None
) -> None:
    vertex_id = None if expected is None else ROOM.vertices[expected].id

    assert edge_at(ROOM, point, tolerance=5) == vertex_id


def test_room_at_prefers_the_topmost_room_and_counts_edges() -> None:
    lower, upper = rect_room(0, 0, 400, 300), rect_room(200, 0, 400, 300)

    assert room_at([lower, upper], (300, 100)) == upper.id
    assert room_at([lower, upper], (0, 150)) == lower.id
    assert room_at([lower, upper], (700, 100)) is None


def test_rect_outline_is_clockwise_from_any_two_corners() -> None:
    assert rect_outline((100, 50), (20, 10)) == [(20, 10), (100, 10), (100, 50), (20, 50)]


def test_placed_at_finds_the_topmost_item_under_a_rotated_footprint() -> None:
    lower = rect_item(200, 90, x=100, y=100)
    upper = rect_item(200, 90, x=100, y=100, rotation=90)  # spans y 0..200 at x 55..145

    assert placed_at([lower, upper], (100, 20)) == upper.id
    assert placed_at([lower, upper], (190, 100)) == lower.id
    assert placed_at([lower, upper], (190, 20)) is None


def test_rubber_band_takes_items_it_touches() -> None:
    a, b = rect_item(100, 100, x=50, y=50), rect_item(100, 100, x=300, y=50)

    assert placed_in_rect([a, b], (120, 120), (90, -10)) == [a.id]
    assert placed_in_rect([a, b], (0, 0), (400, 10)) == [a.id, b.id]


def test_nearest_within_respects_the_tolerance() -> None:
    points = {"a": (0.0, 0.0), "b": (10.0, 0.0)}

    assert nearest_within(points, (7, 0), tolerance=3) == "b"
    assert nearest_within(points, (5, 4), tolerance=3) is None
    assert nearest_within({}, (0, 0), tolerance=3) is None


def test_shape_corners_are_in_world_coordinates() -> None:
    triangle = item(polygon_shape((0, 0), (10, 0), (0, 10)), x=100, y=50, rotation=90)

    assert shape_corners(triangle) == pytest.approx({0: (100, 50), 1: (100, 60), 2: (90, 50)})
    assert shape_corners(rect_item(10, 10)) == {}
