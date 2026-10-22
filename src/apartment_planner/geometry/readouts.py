"""Distance readouts for the selection. See docs/SPEC.md §7.

A readout is a segment (from, to) in world cm; its length is the distance.
"""

import math
from collections.abc import Iterable, Sequence
from typing import Literal

from shapely.ops import nearest_points

from apartment_planner.geometry.shapes import placed_polygon, room_polygon
from apartment_planner.geometry.transform import XY, rotate
from apartment_planner.model import Placed, Room

type Segment = tuple[XY, XY]
Side = Literal["left", "right", "back", "front"]

# Each side's direction in the item's own coordinates (+y is its front).
SIDES: dict[Side, XY] = {"left": (-1, 0), "right": (1, 0), "back": (0, -1), "front": (0, 1)}


def gap_between(a: Placed, b: Placed) -> Segment:
    """The shortest segment between two items' footprints (zero-length if they touch)."""
    pa, pb = nearest_points(placed_polygon(a), placed_polygon(b))
    return (pa.x, pa.y), (pb.x, pb.y)


def wall_gaps(item: Placed, rooms: Sequence[Room]) -> dict[Side, Segment | None]:
    """How far the item could slide along each of its own axes before it reaches a
    wall: a segment from the item to the wall, or None if no wall is that way."""
    corners = _corners(placed_polygon(item).exterior.coords)
    walls = [
        edge for room in rooms for edge in _edges(_corners(room_polygon(room).exterior.coords))
    ]
    return {
        side: _slide(corners, walls, rotate(direction, item.rotation))
        for side, direction in SIDES.items()
    }


def _corners(coords: Iterable[tuple[float, ...]]) -> list[XY]:
    return [(c[0], c[1]) for c in coords][:-1]  # Shapely repeats the first corner


def _edges(corners: list[XY]) -> list[Segment]:
    return list(zip(corners, [*corners[1:], corners[0]], strict=True))


def _slide(corners: list[XY], walls: list[Segment], direction: XY) -> Segment | None:
    """The shortest segment, along `direction`, from the outline to a wall.

    Two kinds of ray find it: from each outline corner forwards to a wall the
    item would move into (walls run clockwise, so their inside is on the right),
    and from each wall corner backwards to the outline, for wall corners that
    poke into the item's path.
    """
    dx, dy = direction
    hits: list[tuple[float, Segment]] = []
    for a, b in walls:
        if dx * -(b[1] - a[1]) + dy * (b[0] - a[0]) >= 0:
            continue  # moving along or away from this wall's inside face
        for corner in corners:
            t = _ray_hit(corner, direction, a, b)
            if t is not None:
                hits.append((t, (corner, (corner[0] + dx * t, corner[1] + dy * t))))
    for end in dict.fromkeys(end for wall in walls for end in wall):
        for a, b in _edges(corners):
            t = _ray_hit(end, (-dx, -dy), a, b)
            if t is not None and t > 0:
                hits.append((t, ((end[0] - dx * t, end[1] - dy * t), end)))
    return min(hits, key=lambda hit: hit[0])[1] if hits else None


def _ray_hit(origin: XY, direction: XY, a: XY, b: XY) -> float | None:
    """How far along the ray from `origin` it meets segment a-b; None if it doesn't.

    A ray running along the segment doesn't count: its ends are other rays' hits.
    """
    ex, ey = b[0] - a[0], b[1] - a[1]
    denominator = direction[0] * ey - direction[1] * ex
    if math.isclose(denominator, 0.0, abs_tol=1e-12):
        return None
    ox, oy = a[0] - origin[0], a[1] - origin[1]
    t = (ox * ey - oy * ex) / denominator
    s = (ox * direction[1] - oy * direction[0]) / denominator
    if t < -1e-9 or not -1e-9 <= s <= 1 + 1e-9:
        return None
    return max(t, 0.0)
