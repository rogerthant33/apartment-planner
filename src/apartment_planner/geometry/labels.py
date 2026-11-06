"""Where a room's name and area label goes: clear of furniture and obstacles."""

import math

import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from apartment_planner.geometry.transform import XY

MAX_STEPS = 60  # candidate positions per side of the room, at most
GAP = 0.25  # space kept between a moved label and what it avoids, in label heights
NOTHING: BaseGeometry = Polygon()  # no blockers


def label_anchor(room: Polygon) -> XY:
    """The label's preferred spot: the room's centroid, or a point inside rooms
    whose centroid falls outside them (an L-shaped room, say)."""
    anchor = room.centroid
    if not room.contains(anchor):
        anchor = room.representative_point()
    return (anchor.x, anchor.y)


def label_position(room: Polygon, blockers: BaseGeometry, size: XY, anchor: XY) -> XY:
    """Where to centre a `size` (width, depth) label in `room`: at `anchor` if it's
    clear of `blockers` there, else the nearest spot where the whole label fits in
    the room clear of them. With no such spot, the spot in the room where the
    label covers the least of them; `anchor` if the label can't fit the room.
    A moved label keeps a gap from walls and blockers."""
    width, depth = size
    if width <= 0 or depth <= 0 or blockers.is_empty:
        return anchor
    gap = depth * GAP
    half_w, half_d = width / 2 + gap, depth / 2 + gap  # the label and the space around it
    x, y = anchor
    if not shapely.box(x - half_w, y - half_d, x + half_w, y + half_d).intersects(blockers):
        return anchor
    min_x, min_y, max_x, max_y = room.bounds
    step = max(min(width, depth) / 2, max(max_x - min_x, max_y - min_y) / MAX_STEPS)
    xs = _steps(min_x + half_w, max_x - half_w, step, through=x)
    ys = _steps(min_y + half_d, max_y - half_d, step, through=y)
    centres = [(cx, cy) for cx in xs for cy in ys]
    labels = shapely.box(
        [cx - half_w for cx, _ in centres],
        [cy - half_d for _, cy in centres],
        [cx + half_w for cx, _ in centres],
        [cy + half_d for _, cy in centres],
    )
    inside = shapely.contains(room, labels)
    covered = shapely.area(shapely.intersection(labels, blockers))
    fits = [
        (area, math.dist(c, anchor), c)
        for c, ok, area in zip(centres, inside, covered, strict=True)
        if ok
    ]
    return min(fits, default=(0.0, 0.0, anchor))[2]  # the least covered, then the nearest


def _steps(start: float, stop: float, step: float, through: float) -> list[float]:
    """Positions `step` apart from `start` to `stop`, in line with `through`."""
    first, last = math.ceil((start - through) / step), math.floor((stop - through) / step)
    return [through + i * step for i in range(first, last + 1)]
