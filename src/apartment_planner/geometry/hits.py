"""Hit testing in world coordinates, so canvas items stay purely visual.

Tolerances are in cm; the canvas converts a fixed distance on screen.
"""

import math
from collections.abc import Callable, Mapping, Sequence

from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import box

from apartment_planner.geometry.shapes import placed_polygon, room_polygon
from apartment_planner.geometry.snapping import nearest_on_segment
from apartment_planner.geometry.transform import XY, local_to_world_all
from apartment_planner.model import Placed, PolygonShape, Room


def vertex_at(room: Room, point: XY, tolerance: float) -> str | None:
    """The ID of the room's vertex nearest to `point`, if within `tolerance`."""
    nearest = min(room.vertices, key=lambda v: math.dist(point, (v.x, v.y)))
    return nearest.id if math.dist(point, (nearest.x, nearest.y)) <= tolerance else None


def edge_at(room: Room, point: XY, tolerance: float) -> str | None:
    """The start vertex ID of the room's edge nearest to `point`, if within `tolerance`."""
    vertices = room.vertices

    def distance(i: int) -> float:
        # `- len` instead of `%` would index the same vertex from the end.
        a, b = vertices[i], vertices[(i + 1) % len(vertices)]  # pragma: no mutate
        return math.dist(point, nearest_on_segment(point, (a.x, a.y), (b.x, b.y)))

    i = min(range(len(vertices)), key=distance)
    return vertices[i].id if distance(i) <= tolerance else None


def room_at(rooms: Sequence[Room], point: XY) -> str | None:
    """The ID of the topmost (last drawn) room containing `point`, edges included."""
    return room_locator(rooms)(point)


def room_locator(rooms: Sequence[Room]) -> Callable[[XY], str | None]:
    """`room_at` for many points: the room polygons are built once."""
    floors = [(room.id, room_polygon(room)) for room in reversed(rooms)]

    def locate(point: XY) -> str | None:
        target = ShapelyPoint(point)
        return next((room_id for room_id, floor in floors if floor.covers(target)), None)

    return locate


def rect_outline(a: XY, b: XY) -> list[XY]:
    """The axis-aligned rectangle with opposite corners `a` and `b`, clockwise on screen."""
    left, right = sorted((a[0], b[0]))
    top, bottom = sorted((a[1], b[1]))
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def placed_at(items: Sequence[Placed], point: XY) -> str | None:
    """The ID of the topmost (last drawn) furniture item or obstacle containing `point`."""
    target = ShapelyPoint(point)
    for item in reversed(items):
        if placed_polygon(item).covers(target):
            return item.id
    return None


def placed_in_rect(items: Sequence[Placed], a: XY, b: XY) -> list[str]:
    """IDs of the items a rubber band from `a` to `b` touches."""
    band = box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
    return [item.id for item in items if placed_polygon(item).intersects(band)]


def nearest_within[K](points: Mapping[K, XY], point: XY, tolerance: float) -> K | None:
    """The key of the point nearest to `point`, if within `tolerance`."""
    if not points:
        return None
    key = min(points, key=lambda k: math.dist(point, points[k]))
    return key if math.dist(point, points[key]) <= tolerance else None


def shape_corners(item: Placed) -> dict[int, XY]:
    """World positions of a polygon item's corners, by index (empty for other shapes)."""
    if not isinstance(item.shape, PolygonShape):
        return {}
    points = [(p.x, p.y) for p in item.shape.points]
    world = local_to_world_all(points, (item.x, item.y), item.rotation)
    return dict(enumerate(world))
