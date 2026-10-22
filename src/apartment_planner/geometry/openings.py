"""Where openings sit on their walls, and the area a door sweeps. See docs/SPEC.md §5.

Rooms run clockwise on screen (y down), so the inside of each edge is on the
right of its direction: the inward normal of (dx, dy) is (-dy, dx).
"""

import math
from collections.abc import Sequence

from shapely.geometry import Polygon

from apartment_planner.geometry.constants import ELLIPSE_SEGMENTS, EPS
from apartment_planner.geometry.snapping import nearest_on_segment
from apartment_planner.geometry.transform import XY
from apartment_planner.model import Opening, Room

ARC_SEGMENTS = ELLIPSE_SEGMENTS // 4  # a quarter of the shared circle resolution


def edge(room: Room, start_vertex_id: str) -> tuple[XY, XY]:
    """The edge running from this vertex to the next one."""
    vertices = room.vertices
    for i, vertex in enumerate(vertices):
        if vertex.id == start_vertex_id:
            # `- len` instead of `%` would index the same vertex from the end.
            end = vertices[(i + 1) % len(vertices)]  # pragma: no mutate
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
    # pragmas below: hinge and swing are validated Literals, which pydantic returns as
    # the literal objects themselves, and "end" < "start", "in" < "out". So `is` and
    # `>=` mutants behave the same.
    hinged_at_start = opening.door.hinge == "start"  # pragma: no mutate
    hinge, tip = (start, end) if hinged_at_start else (end, start)
    nx, ny = inward_normal(*edge(room, opening.edge_start_vertex_id))
    if opening.door.swing == "out":  # pragma: no mutate
        nx, ny = -nx, -ny
    closed = (tip[0] - hinge[0], tip[1] - hinge[1])  # the leaf lying in the doorway
    radius = opening.width
    opened = (nx * radius, ny * radius)
    arc = []
    # ARC_SEGMENTS is even, so `| 1` and `^ 1` mutants equal `+ 1`.
    for i in range(ARC_SEGMENTS + 1):  # pragma: no mutate
        t = math.pi / 2 * i / ARC_SEGMENTS
        arc.append(
            (
                hinge[0] + closed[0] * math.cos(t) + opened[0] * math.sin(t),
                hinge[1] + closed[1] * math.cos(t) + opened[1] * math.sin(t),
            )
        )
    return Polygon([hinge, *arc])


def wall_pieces(
    room: Room, openings: Sequence[Opening], start_vertex_id: str
) -> list[tuple[float, float, bool]]:
    """An edge split by its openings, in order along it: (from, to, is_opening),
    in cm from the edge start. Empty if no opening is on the edge.

    Openings are clamped to the edge, and ones that overlap are taken as one.
    """
    a, b = edge(room, start_vertex_id)
    length = math.dist(a, b)
    spans = sorted(
        (max(o.offset - o.width / 2, 0.0), min(o.offset + o.width / 2, length))
        for o in openings
        if o.room_id == room.id and o.edge_start_vertex_id == start_vertex_id
    )
    merged: list[tuple[float, float]] = []
    for span_start, span_end in spans:
        if merged and span_start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], span_end))
        else:
            merged.append((span_start, span_end))
    pieces: list[tuple[float, float, bool]] = []
    cursor = 0.0
    for span_start, span_end in merged:
        if span_start > cursor + EPS:
            pieces.append((cursor, span_start, False))
        pieces.append((span_start, span_end, True))
        cursor = span_end
    if merged and cursor < length - EPS:
        pieces.append((cursor, length, False))
    return pieces


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


def opening_at(
    rooms: list[Room], openings: list[Opening], point: XY, tolerance: float
) -> str | None:
    """The ID of the opening whose span passes within `tolerance` of `point`."""
    by_id = {room.id: room for room in rooms}
    best: tuple[float, str] | None = None
    for candidate in openings:
        a, b = opening_span(by_id[candidate.room_id], candidate)
        distance = math.dist(point, nearest_on_segment(point, a, b))
        if distance <= tolerance and (best is None or distance < best[0]):
            best = (distance, candidate.id)
    return None if best is None else best[1]
