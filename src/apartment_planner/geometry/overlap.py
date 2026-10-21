"""Tolerance-aware spatial relations between valid polygons."""

from collections.abc import Iterable

from shapely import unary_union
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from apartment_planner.geometry.constants import EPS


class InvalidGeometryError(ValueError):
    """Raised when a relation is asked of a polygon that isn't valid."""


def _require_valid(*polygons: BaseGeometry) -> None:
    for polygon in polygons:
        if polygon.is_empty or not polygon.is_valid:
            raise InvalidGeometryError("Spatial checks need valid, non-empty polygons.")


def is_substantial(region: BaseGeometry, eps: float = EPS) -> bool:
    """True if the region contains a disk of diameter `eps`.

    Lines, points and slivers thinner than `eps` (including floating-point
    noise along shared edges) are not substantial.
    """
    if region.is_empty:
        return False
    return not region.buffer(-eps / 2).is_empty


def overlaps(a: Polygon, b: Polygon, eps: float = EPS) -> bool:
    """True if a and b overlap by more than `eps`. Touching doesn't count."""
    _require_valid(a, b)
    if not a.intersects(b):
        return False
    return is_substantial(a.intersection(b), eps)


def outside(item: Polygon, containers: Iterable[Polygon], eps: float = EPS) -> bool:
    """True if more than `eps` of the item lies outside the union of the containers."""
    regions = list(containers)
    _require_valid(item, *regions)
    if not regions:
        return True
    return is_substantial(item.difference(unary_union(regions)), eps)


def distance(a: Polygon, b: Polygon) -> float:
    """Minimum distance between two polygons in cm; 0 if they touch or overlap."""
    _require_valid(a, b)
    return float(a.distance(b))
