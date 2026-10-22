"""Model objects to Shapely geometry. Build footprints only through these helpers."""

import math
from collections.abc import Iterable, Sequence

from shapely.geometry import MultiPoint, Polygon

from apartment_planner.geometry.constants import ELLIPSE_SEGMENTS
from apartment_planner.geometry.polygon import points_polygon
from apartment_planner.geometry.transform import XY, local_to_world_all
from apartment_planner.model import (
    EllipseShape,
    Placed,
    Point,
    PolygonShape,
    RectShape,
    Room,
    Shape,
)

_UNIT_CIRCLE = [
    (math.cos(2 * math.pi * i / ELLIPSE_SEGMENTS), math.sin(2 * math.pi * i / ELLIPSE_SEGMENTS))
    for i in range(ELLIPSE_SEGMENTS)
]


def shape_outline(shape: Shape) -> list[XY]:
    """Outline of a shape in its local coordinates, before rotation."""
    match shape:
        case RectShape(width=w, depth=d):
            hw, hd = w / 2, d / 2
            return [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
        case EllipseShape(rx=rx, ry=ry):
            return [(rx * c, ry * s) for c, s in _UNIT_CIRCLE]
        case PolygonShape(points=points):
            return [(p.x, p.y) for p in points]


def placed_polygon(item: Placed) -> Polygon:
    """World-space footprint of a furniture item or obstacle."""
    return Polygon(local_to_world_all(shape_outline(item.shape), (item.x, item.y), item.rotation))


def room_polygon(room: Room) -> Polygon:
    return points_polygon(room.vertices)


def plan_bounds(
    rooms: Iterable[Room], items: Iterable[Placed], points: Sequence[XY] = ()
) -> tuple[float, float, float, float] | None:
    """(left, top, right, bottom) around the rooms, items and extra points; None if
    there's nothing."""
    boxes = [room_polygon(r).bounds for r in rooms] + [placed_polygon(i).bounds for i in items]
    if points:
        boxes.append(MultiPoint(points).bounds)
    if not boxes:
        return None
    lefts, tops, rights, bottoms = zip(*boxes, strict=True)
    return min(lefts), min(tops), max(rights), max(bottoms)


def l_shape(width: float, depth: float, arm_width: float, arm_depth: float) -> PolygonShape:
    """An L-shaped polygon centred on its bounding box.

    The long side runs along the top (`width`), and the arm hangs down on the
    left (`arm_width` wide) to a total `depth`. The top bar is `arm_depth` deep.
    """
    if not (0 < arm_width < width and 0 < arm_depth < depth):
        raise ValueError("The L-shape's arm must be narrower and shallower than the whole shape.")
    hw, hd = width / 2, depth / 2
    corners = [
        (-hw, -hd),
        (hw, -hd),
        (hw, -hd + arm_depth),
        (-hw + arm_width, -hd + arm_depth),
        (-hw + arm_width, hd),
        (-hw, hd),
    ]
    return PolygonShape(points=tuple(Point(x=x, y=y) for x, y in corners))
