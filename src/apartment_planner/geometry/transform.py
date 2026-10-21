"""Rotation and local/world transforms.

World space has +y pointing down, so a positive angle turns clockwise on
screen, matching Qt's QGraphicsItem.setRotation.
"""

import math

XY = tuple[float, float]


def rotate(point: XY, degrees: float) -> XY:
    """Rotate a point about the origin, clockwise on screen."""
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    x, y = point
    return (x * cos - y * sin, x * sin + y * cos)


def local_to_world(point: XY, origin: XY, rotation: float) -> XY:
    rx, ry = rotate(point, rotation)
    return (rx + origin[0], ry + origin[1])


def world_to_local(point: XY, origin: XY, rotation: float) -> XY:
    return rotate((point[0] - origin[0], point[1] - origin[1]), -rotation)
