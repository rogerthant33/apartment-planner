"""Point snapping in world coordinates. See docs/SPEC.md §5 "Rooms".

Priority: other rooms' vertices, then their edges, then the grid. Vertices and
edges only attract within `tolerance` cm, which the canvas derives from a fixed
distance on screen.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from apartment_planner.geometry.transform import XY
from apartment_planner.model import Room


class SnapKind(StrEnum):
    VERTEX = "vertex"
    EDGE = "edge"
    GRID = "grid"
    NONE = "none"


@dataclass(frozen=True)  # pragma: no mutate (immutability is a convention; nothing assigns)
class Snapped:
    point: XY
    kind: SnapKind


@dataclass(frozen=True)  # pragma: no mutate (as above)
class SnapTargets:
    vertices: tuple[XY, ...] = ()
    edges: tuple[tuple[XY, XY], ...] = ()


def room_targets(rooms: Iterable[Room], exclude: str | None = None) -> SnapTargets:
    """Vertices and edges of every room except `exclude` (the one being edited)."""
    vertices: list[XY] = []
    edges: list[tuple[XY, XY]] = []
    for room in rooms:
        if room.id == exclude:
            continue
        corners = [(v.x, v.y) for v in room.vertices]
        vertices.extend(corners)
        # Both sides have len(corners) items by construction.
        edges.extend(zip(corners, [*corners[1:], corners[0]], strict=True))  # pragma: no mutate
    return SnapTargets(tuple(vertices), tuple(edges))


def nearest_on_segment(point: XY, a: XY, b: XY) -> XY:
    (px, py), (ax, ay), (bx, by) = point, a, b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:  # pragma: no mutate (a squared length is never negative)
        return a
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = min(max(t, 0.0), 1.0)
    return (ax + t * dx, ay + t * dy)


def snap_to_grid(point: XY, grid: float) -> XY:
    return (round(point[0] / grid) * grid, round(point[1] / grid) * grid)


# `*` → `/` still accepts every call that passes grid and tolerance by keyword.
def snap(
    point: XY,
    targets: SnapTargets,
    *,  # pragma: no mutate
    grid: float | None,
    tolerance: float,
) -> Snapped:
    """`point` moved to the best snap target, or unchanged if nothing applies.

    `grid` is None when grid snapping is off.
    """
    vertex = _nearest(point, targets.vertices)
    if vertex is not None and math.dist(point, vertex) <= tolerance:
        return Snapped(vertex, SnapKind.VERTEX)
    on_edge = _nearest(point, [nearest_on_segment(point, a, b) for a, b in targets.edges])
    if on_edge is not None and math.dist(point, on_edge) <= tolerance:
        return Snapped(on_edge, SnapKind.EDGE)
    if grid is not None:
        return Snapped(snap_to_grid(point, grid), SnapKind.GRID)
    return Snapped(point, SnapKind.NONE)


def _nearest(point: XY, candidates: Iterable[XY]) -> XY | None:
    return min(candidates, key=lambda c: math.dist(point, c), default=None)
