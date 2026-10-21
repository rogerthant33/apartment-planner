"""Plain polygon maths on vertex sequences, and polygon validation.

The model imports this module, so it must not import `apartment_planner.model`.
"""

import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

from shapely.geometry import Polygon
from shapely.validation import make_valid

from apartment_planner.geometry.constants import MIN_EDGE_LENGTH
from apartment_planner.geometry.overlap import is_substantial
from apartment_planner.geometry.transform import HasXY


def points_polygon(points: Iterable[HasXY]) -> Polygon:
    return Polygon([(p.x, p.y) for p in points])


def _edges[T: HasXY](points: Sequence[T]) -> Iterator[tuple[T, T]]:
    """Each edge as (start, end), wrapping from the last point to the first."""
    # Both sides have len(points) items by construction.
    return zip(points, [*points[1:], points[0]], strict=True)  # pragma: no mutate


def signed_area(points: Sequence[HasXY]) -> float:
    """Shoelace area. Positive when the points run clockwise on screen (y down).

    Note this is the opposite of Shapely's `is_ccw`, which assumes y up.
    """
    return sum(a.x * b.y - b.x * a.y for a, b in _edges(points)) / 2.0


def is_clockwise(points: Sequence[HasXY]) -> bool:
    """Clockwise on screen. Degenerate (zero-area) outlines count as clockwise."""
    return signed_area(points) >= 0


def edge_lengths(points: Sequence[HasXY]) -> list[float]:
    """Length of each edge i, running from points[i] to points[i + 1] (wrapping)."""
    return [math.hypot(b.x - a.x, b.y - a.y) for a, b in _edges(points)]


class IssueKind(StrEnum):
    TOO_FEW_VERTICES = "too_few_vertices"
    SHORT_EDGE = "short_edge"
    SELF_INTERSECTION = "self_intersection"
    NO_AREA = "no_area"


@dataclass(frozen=True)  # pragma: no mutate (immutability is a convention; nothing assigns)
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

    polygon = points_polygon(points)
    if not is_substantial(make_valid(polygon)):
        issues.append(PolygonIssue(IssueKind.NO_AREA, "The shape has no area."))
    elif not polygon.is_valid:
        issues.append(
            PolygonIssue(
                IssueKind.SELF_INTERSECTION,
                "The outline crosses itself. Move a corner so no edges cross.",
            )
        )
    return issues
