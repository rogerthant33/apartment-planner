"""Tolerance-aware spatial relations.

Inputs must be valid polygons (see `validate_polygon`). Callers check validity
once when building footprints, not on every pairwise call.
"""

import math

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from apartment_planner.geometry.constants import EPS


def is_substantial(region: BaseGeometry, eps: float = EPS) -> bool:
    """True if the region contains a disk of diameter `eps`.

    Lines, points and slivers thinner than `eps` (including floating-point
    noise along shared edges) are not substantial.
    """
    # Too small to hold the disk at all; also skips the buffer for touching edges.
    # Only a shortcut: the buffer test below gives the same answer.
    if region.area < math.pi * eps**2 / 4:  # pragma: no mutate
        return False
    return not region.buffer(-eps / 2).is_empty


def overlaps(a: Polygon, b: Polygon, eps: float = EPS) -> bool:
    """True if a and b overlap by more than `eps`. Touching doesn't count."""
    return a.intersects(b) and is_substantial(a.intersection(b), eps)


def outside(item: Polygon, container: BaseGeometry, eps: float = EPS) -> bool:
    """True if more than `eps` of the item lies outside the container.

    The container is usually the union of all rooms, built once per check run.
    """
    if container.contains(item):
        return False
    return is_substantial(item.difference(container), eps)


def distance(a: Polygon, b: Polygon) -> float:
    """Minimum distance between two polygons in cm; 0 if they touch or overlap."""
    return float(a.distance(b))
