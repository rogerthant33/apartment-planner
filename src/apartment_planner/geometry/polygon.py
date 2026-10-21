"""Plain polygon maths on vertex sequences, and polygon validation."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from shapely.geometry import Polygon
from shapely.validation import explain_validity

from apartment_planner.geometry.constants import MIN_EDGE_LENGTH


class HasXY(Protocol):
    @property
    def x(self) -> float: ...
    @property
    def y(self) -> float: ...


def signed_area(points: Sequence[HasXY]) -> float:
    """Shoelace area. Positive when the points run clockwise on screen (y down).

    Note this is the opposite of Shapely's `is_ccw`, which assumes y up.
    """
    total = 0.0
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        total += a.x * b.y - b.x * a.y
    return total / 2.0


def ensure_clockwise[T: HasXY](points: Sequence[T]) -> tuple[T, ...]:
    """Return the points in clockwise-on-screen order, reversing if needed."""
    return tuple(points) if signed_area(points) >= 0 else tuple(reversed(points))


def edge_lengths(points: Sequence[HasXY]) -> list[float]:
    """Length of each edge i, running from points[i] to points[i + 1] (wrapping)."""
    return [
        math.hypot(points[(i + 1) % len(points)].x - p.x, points[(i + 1) % len(points)].y - p.y)
        for i, p in enumerate(points)
    ]


class IssueKind(StrEnum):
    TOO_FEW_VERTICES = "too_few_vertices"
    SHORT_EDGE = "short_edge"
    SELF_INTERSECTION = "self_intersection"
    NO_AREA = "no_area"


@dataclass(frozen=True)
class PolygonIssue:
    kind: IssueKind
    message: str
    edge_index: int | None = None


def validate_polygon(points: Sequence[HasXY]) -> list[PolygonIssue]:
    """Problems that make the polygon unusable as a room or shape. Empty means valid."""
    if len(points) < 3:
        return [PolygonIssue(IssueKind.TOO_FEW_VERTICES, "A shape needs at least 3 corners.")]

    issues = [
        PolygonIssue(
            IssueKind.SHORT_EDGE,
            f"Edge {i + 1} is {length:.2f} cm long; edges must be at least {MIN_EDGE_LENGTH:g} cm.",
            edge_index=i,
        )
        for i, length in enumerate(edge_lengths(points))
        if length < MIN_EDGE_LENGTH
    ]

    polygon = Polygon([(p.x, p.y) for p in points])
    # A polygon thinner than a minimum edge in every direction has no usable area.
    min_area = MIN_EDGE_LENGTH**2
    if polygon.convex_hull.area < min_area or (polygon.is_valid and polygon.area < min_area):
        issues.append(PolygonIssue(IssueKind.NO_AREA, "The shape has no area."))
    elif not polygon.is_valid:
        issues.append(
            PolygonIssue(
                IssueKind.SELF_INTERSECTION,
                f"The outline crosses itself ({explain_validity(polygon)}).",
            )
        )
    return issues
