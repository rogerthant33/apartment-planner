"""Where openings sit on their walls, and the area a door sweeps. See docs/SPEC.md §5.

Rooms run clockwise on screen (y down), so the inside of each edge is on the
right of its direction: the inward normal of (dx, dy) is (-dy, dx).
"""

import math

from shapely.geometry import Polygon

from apartment_planner.geometry.constants import ELLIPSE_SEGMENTS
from apartment_planner.geometry.snapping import nearest_on_segment
from apartment_planner.geometry.transform import XY
from apartment_planner.model import Opening, Room

ARC_SEGMENTS = ELLIPSE_SEGMENTS // 4  # a quarter of the shared circle resolution


def edge(room: Room, start_vertex_id: str) -> tuple[XY, XY]:
    """The edge running from this vertex to the next one."""
    vertices = room.vertices
    for i, vertex in enumerate(vertices):
        if vertex.id == start_vertex_id:
            end = vertices[(i + 1) % len(vertices)]
            return (vertex.x, vertex.y), (end.x, end.y)
    raise KeyError(start_vertex_id)


def _unit(a: XY, b: XY) -> XY:
    length = math.dist(a, b)
    return ((b[0] - a[0]) / length, (b[1] - a[1]) / length)


def inward_normal(a: XY, b: XY) -> XY:
    """The unit vector from the edge a→b into its (clockwise) room."""
    dx, dy = _unit(a, b)
    return (-dy, dx)


def opening_span(room: Room, opening: Opening) -> tuple[XY, XY]:
    """The opening's two ends on its wall, in the edge's direction."""
    a, b = edge(room, opening.edge_start_vertex_id)
    dx, dy = _unit(a, b)
    start = opening.offset - opening.width / 2
    end = opening.offset + opening.width / 2
    return (a[0] + dx * start, a[1] + dy * start), (a[0] + dx * end, a[1] + dy * end)


def door_swing(room: Room, opening: Opening) -> Polygon:
    """The quarter circle a door leaf sweeps, from closed (along the wall) to open.

    The leaf turns on its hinge (the span's start or end) into the room
    (`swing="in"`) or away from it.
    """
    if opening.door is None:
        raise ValueError("Only doors swing")
    start, end = opening_span(room, opening)
    hinge, tip = (start, end) if opening.door.hinge == "start" else (end, start)
    nx, ny = inward_normal(*edge(room, opening.edge_start_vertex_id))
    if opening.door.swing == "out":
        nx, ny = -nx, -ny
    closed = (tip[0] - hinge[0], tip[1] - hinge[1])  # the leaf lying in the doorway
    radius = opening.width
    opened = (nx * radius, ny * radius)
    arc = []
    for i in range(ARC_SEGMENTS + 1):
        t = math.pi / 2 * i / ARC_SEGMENTS
        arc.append(
            (
                hinge[0] + closed[0] * math.cos(t) + opened[0] * math.sin(t),
                hinge[1] + closed[1] * math.cos(t) + opened[1] * math.sin(t),
            )
        )
    return Polygon([hinge, *arc])


def nearest_edge(rooms: list[Room], point: XY, tolerance: float) -> tuple[Room, str, float] | None:
    """The room edge nearest to `point` within `tolerance`: the room, the edge's start
    vertex ID, and how far along the edge the point projects (cm from its start)."""
    best: tuple[float, Room, str, float] | None = None
    for room in rooms:
        for vertex in room.vertices:
            a, b = edge(room, vertex.id)
            on_edge = nearest_on_segment(point, a, b)
            distance = math.dist(point, on_edge)
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, room, vertex.id, math.dist(a, on_edge))
    return None if best is None else best[1:]
