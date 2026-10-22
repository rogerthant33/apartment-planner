"""Point snapping in world coordinates. See docs/SPEC.md §5 "Rooms".

Priority: other rooms' vertices, then their edges, then the grid. Vertices and
edges only attract within `tolerance` cm, which the canvas derives from a fixed
distance on screen.
"""

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from apartment_planner.geometry.constants import EPS
from apartment_planner.geometry.shapes import shape_outline
from apartment_planner.geometry.transform import XY, local_to_world_all
from apartment_planner.model import Placed, Room


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


def placed_edges(items: Iterable[Placed]) -> list[tuple[XY, XY]]:
    """The footprint edges of furniture items or obstacles, for snapping against."""
    edges: list[tuple[XY, XY]] = []
    for item in items:
        corners = local_to_world_all(shape_outline(item.shape), (item.x, item.y), item.rotation)
        edges.extend(zip(corners, [*corners[1:], corners[0]], strict=True))  # pragma: no mutate
    return edges


def snap_move(
    corners: Sequence[XY],
    anchor: XY,
    delta: XY,
    edges: Sequence[tuple[XY, XY]],
    *,  # pragma: no mutate (as for `snap`)
    grid: float | None,
    tolerance: float,
) -> XY:
    """Adjust a move by `delta` of an outline with these `corners`.

    If a moved corner comes within `tolerance` of an edge (a wall or another
    item), the outline moves flush against the nearest such edge, and then slides
    along it onto a second edge within `tolerance`, if there is one: into a corner
    of the room, say. Otherwise `anchor` (the item's origin) lands on the grid, when
    there is one.
    """
    dx, dy = delta
    found = _closest(corners, delta, lambda moved: _on_edges(moved, edges), tolerance)
    if found is not None:
        (sx, sy), (a, b) = found
        flush = (dx + sx, dy + sy)
        length = math.dist(a, b)
        if length == 0:  # a degenerate edge is a point: no direction to slide in
            return flush
        along = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        slide = _slide_onto(corners, flush, along, edges, tolerance)
        return (flush[0] + along[0] * slide, flush[1] + along[1] * slide)
    if grid is not None:
        gx, gy = snap_to_grid((anchor[0] + dx, anchor[1] + dy), grid)
        return (gx - anchor[0], gy - anchor[1])
    return delta


def snap_room_move(
    corners: Sequence[XY],
    delta: XY,
    targets: SnapTargets,
    *,  # pragma: no mutate (as for `snap`)
    grid: float | None,
    tolerance: float,
) -> XY:
    """Adjust a move by `delta` of rooms with these `corners`.

    A moved corner within `tolerance` of another room's corner lands on it;
    otherwise the rooms move as `snap_move` moves furniture: flush against the
    nearest edge in reach (and on into a corner it makes), or else the first
    corner lands on the grid.
    """
    dx, dy = delta
    found = _closest(corners, delta, lambda _: ((v, v) for v in targets.vertices), tolerance)
    if found is not None:
        return (dx + found[0][0], dy + found[0][1])
    return snap_move(corners, corners[0], delta, targets.edges, grid=grid, tolerance=tolerance)


def _closest[T](
    corners: Sequence[XY],
    delta: XY,
    targets_for: Callable[[XY], Iterable[tuple[XY, T]]],
    tolerance: float,
) -> tuple[XY, T] | None:
    """The shortest further shift that puts a moved corner on one of its targets,
    within `tolerance`, and what that target came from; the first found wins a tie.
    None if none is in reach."""
    dx, dy = delta
    best: tuple[float, XY, T] | None = None
    for x, y in corners:
        moved = (x + dx, y + dy)
        for target, source in targets_for(moved):
            distance = math.dist(moved, target)
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, (target[0] - moved[0], target[1] - moved[1]), source)
    return None if best is None else (best[1], best[2])


def _on_edges(point: XY, edges: Iterable[tuple[XY, XY]]) -> Iterable[tuple[XY, tuple[XY, XY]]]:
    return ((nearest_on_segment(point, a, b), (a, b)) for a, b in edges)


def _slide_onto(
    corners: Sequence[XY], delta: XY, along: XY, edges: Sequence[tuple[XY, XY]], tolerance: float
) -> float:
    """How far (either way along `along`, within `tolerance`) to slide the moved
    corners so one lands on an edge that crosses that direction; 0 if none is in
    reach. The shortest slide wins; the first found wins a tie."""
    ux, uy = along
    best: float | None = None
    for x, y in corners:
        px, py = x + delta[0], y + delta[1]
        for (ax, ay), (bx, by) in edges:
            ex, ey = bx - ax, by - ay
            denominator = ux * ey - uy * ex  # the edge's length times the sine between them
            if abs(denominator) * tolerance <= EPS * math.hypot(ex, ey):
                # (Nearly) parallel to the slide, such as the edge it's flush against:
                # within reach it strays less than EPS from it, so it's no corner.
                continue
            ox, oy = ax - px, ay - py
            t = (ox * ey - oy * ex) / denominator
            s = (ox * uy - oy * ux) / denominator
            if 0 <= s <= 1 and abs(t) <= tolerance and (best is None or abs(t) < abs(best)):
                best = t
    return 0.0 if best is None else best
