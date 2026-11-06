"""Where a room's name and area label goes: clear of furniture and obstacles."""

import math

import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from apartment_planner.geometry.transform import XY

MAX_STEPS = 60  # candidate positions per side of the room, at most
GAP = 0.25  # space kept between a moved label and what it avoids, in label heights
BATCH = 256  # candidate positions tested together


def label_anchor(room: Polygon) -> XY:
    """The label's preferred spot: the room's centroid, or a point inside rooms
    whose centroid falls outside them (an L-shaped room, say)."""
    anchor = room.centroid
    if not room.contains(anchor):
        anchor = room.representative_point()
    return (anchor.x, anchor.y)


def label_position(room: Polygon, blockers: BaseGeometry, size: XY, anchor: XY | None = None) -> XY:
    """Where to centre a `size` (width, depth) label in `room`: at `anchor` if it's
    clear of `blockers` there, else the nearest spot where the whole label fits in
    the room clear of them. With no such spot, the spot in the room where the
    label covers the least of them; `anchor` if the label can't fit the room.
    It's quicker with a prepared `room` (`shapely.prepare`).
    A moved label keeps a gap from walls and blockers. `anchor` defaults to
    `label_anchor(room)`."""
    if anchor is None:
        anchor = label_anchor(room)
    width, depth = size
    if width <= 0 or depth <= 0 or blockers.is_empty:
        return anchor
    gap = depth * GAP
    half_w, half_d = width / 2 + gap, depth / 2 + gap  # the label and the space around it
    x, y = anchor
    if not shapely.box(x - half_w, y - half_d, x + half_w, y + half_d).intersects(blockers):
        return anchor
    min_x, min_y, max_x, max_y = room.bounds
    nearby = shapely.clip_by_rect(blockers, min_x, min_y, max_x, max_y)
    shapely.prepare(nearby)
    step = max(min(width, depth) / 2, max(max_x - min_x, max_y - min_y) / MAX_STEPS)
    xs = _steps(min_x + half_w, max_x - half_w, step, through=x)
    ys = _steps(min_y + half_d, max_y - half_d, step, through=y)
    # Nearest first, a batch at a time: a clear spot is usually close by.
    centres = sorted(((cx, cy) for cx in xs for cy in ys), key=lambda c: math.dist(c, anchor))
    in_room: list[XY] = []  # spots in the room, all overlapping something
    for start in range(0, len(centres), BATCH):
        batch = centres[start : start + BATCH]
        boxes = shapely.box(
            [cx - half_w for cx, _ in batch],
            [cy - half_d for _, cy in batch],
            [cx + half_w for cx, _ in batch],
            [cy + half_d for _, cy in batch],
        )
        inside = shapely.contains(room, boxes)
        hit = shapely.intersects(nearby, boxes)
        for centre, ok, blocked in zip(batch, inside, hit, strict=True):
            if ok and not blocked:
                return centre
            if ok:
                in_room.append(centre)

    # Nowhere clear: the least covered spot (the nearest of equals, as they're sorted).
    # Clipping to the label's box is much cheaper than a general intersection.
    def covered(spot: XY) -> float:
        cx, cy = spot
        box = (cx - half_w, cy - half_d, cx + half_w, cy + half_d)
        return float(shapely.area(shapely.clip_by_rect(nearby, *box)))

    return min(in_room, key=covered, default=anchor)


def _steps(start: float, stop: float, step: float, through: float) -> list[float]:
    """Positions `step` apart from `start` to `stop`, in line with `through`."""
    first, last = math.ceil((start - through) / step), math.floor((stop - through) / step)
    return [through + i * step for i in range(first, last + 1)]
