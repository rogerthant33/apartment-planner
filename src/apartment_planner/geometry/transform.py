"""Rotation and local/world transforms.

World space has +y pointing down, so a positive angle turns clockwise on
screen, matching Qt's QGraphicsItem.setRotation.
"""

import math
from collections.abc import Iterable
from typing import Protocol

XY = tuple[float, float]


class HasXY(Protocol):
    # Read-only for the type checker only; no runtime effect.
    @property  # pragma: no mutate
    def x(self) -> float: ...
    @property  # pragma: no mutate
    def y(self) -> float: ...


def rotate_all(points: Iterable[XY], degrees: float) -> list[XY]:
    """Rotate points about the origin, clockwise on screen."""
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    return [(x * cos - y * sin, x * sin + y * cos) for x, y in points]


def rotate(point: XY, degrees: float) -> XY:
    return rotate_all([point], degrees)[0]  # pragma: no mutate (one item: [0] is [-1])


def local_to_world_all(points: Iterable[XY], origin: XY, rotation: float) -> list[XY]:
    ox, oy = origin
    return [(x + ox, y + oy) for x, y in rotate_all(points, rotation)]


def local_to_world(point: XY, origin: XY, rotation: float) -> XY:
    return local_to_world_all([point], origin, rotation)[0]  # pragma: no mutate (one item)


def world_to_local(point: XY, origin: XY, rotation: float) -> XY:
    return rotate((point[0] - origin[0], point[1] - origin[1]), -rotation)
