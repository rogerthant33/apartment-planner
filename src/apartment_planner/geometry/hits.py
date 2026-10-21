"""Hit testing in world coordinates, so canvas items stay purely visual.

Tolerances are in cm; the canvas converts a fixed distance on screen.
"""

import math
from collections.abc import Sequence

from shapely.geometry import Point as ShapelyPoint

from apartment_planner.geometry.shapes import room_polygon
from apartment_planner.geometry.snapping import nearest_on_segment
from apartment_planner.geometry.transform import XY
from apartment_planner.model import Room


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
    target = ShapelyPoint(point)
    for room in reversed(rooms):
        if room_polygon(room).covers(target):
            return room.id
    return None


def rect_outline(a: XY, b: XY) -> list[XY]:
    """The axis-aligned rectangle with opposite corners `a` and `b`, clockwise on screen."""
    left, right = sorted((a[0], b[0]))
    top, bottom = sorted((a[1], b[1]))
    return [(left, top), (right, top), (right, bottom), (left, bottom)]
