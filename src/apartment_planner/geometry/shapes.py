"""The only place model objects become Shapely geometry."""

import math

from shapely.geometry import Polygon

from apartment_planner.geometry.constants import ELLIPSE_SEGMENTS
from apartment_planner.geometry.transform import XY, local_to_world
from apartment_planner.model import (
    EllipseShape,
    Placed,
    Point,
    PolygonShape,
    RectShape,
    Room,
    Shape,
)


def shape_outline(shape: Shape) -> list[XY]:
    """Outline of a shape in its local coordinates, before rotation."""
    match shape:
        case RectShape(width=w, depth=d):
            hw, hd = w / 2, d / 2
            return [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
        case EllipseShape(rx=rx, ry=ry):
            step = 2 * math.pi / ELLIPSE_SEGMENTS
            return [
                (rx * math.cos(i * step), ry * math.sin(i * step)) for i in range(ELLIPSE_SEGMENTS)
            ]
        case PolygonShape(points=points):
            return [(p.x, p.y) for p in points]


def placed_polygon(item: Placed) -> Polygon:
    """World-space footprint of a furniture item or obstacle."""
    origin = (item.x, item.y)
    return Polygon([local_to_world(p, origin, item.rotation) for p in shape_outline(item.shape)])


def room_polygon(room: Room) -> Polygon:
    return Polygon([(v.x, v.y) for v in room.vertices])


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
