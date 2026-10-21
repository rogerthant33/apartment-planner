import pytest

from apartment_planner.geometry.hits import edge_at, rect_outline, room_at, vertex_at
from tests.factories import rect_room

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
