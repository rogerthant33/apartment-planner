import pytest

from apartment_planner.geometry.polygon import (
    IssueKind,
    PolygonIssue,
    edge_lengths,
    is_clockwise,
    signed_area,
    validate_polygon,
)
from apartment_planner.geometry.shapes import l_shape
from apartment_planner.geometry.transform import rotate
from tests.factories import points

# Top-left, top-right, bottom-right, bottom-left: clockwise on screen (y down).
SQUARE_CW = points((0, 0), (100, 0), (100, 100), (0, 100))


def kinds(issues: list[PolygonIssue]) -> list[IssueKind]:
    return [i.kind for i in issues]


def test_signed_area_is_positive_for_clockwise_on_screen() -> None:
    assert signed_area(SQUARE_CW) == pytest.approx(10_000)
    assert signed_area(tuple(reversed(SQUARE_CW))) == pytest.approx(-10_000)
    assert signed_area(points((0, 0), (3, 0), (0, 3))) == pytest.approx(4.5)


def test_is_clockwise_treats_zero_area_as_clockwise() -> None:
    assert is_clockwise(SQUARE_CW)
    assert not is_clockwise(tuple(reversed(SQUARE_CW)))
    assert is_clockwise(points((0, 0), (50, 0), (100, 0)))
    # Counter-clockwise with an area of only 0.5 cm².
    assert not is_clockwise(points((0, 0), (0, 1), (1, 0)))


def test_edge_lengths_wrap_around() -> None:
    assert edge_lengths(points((0, 0), (30, 0), (30, 40))) == pytest.approx([30, 40, 50])


def test_concave_l_shape_is_valid() -> None:
    assert validate_polygon(l_shape(200, 160, 80, 80).points) == []


@pytest.mark.parametrize("angle", [0, 37])
def test_rotated_square_is_valid(angle: float) -> None:
    rotated = points(*(rotate((p.x, p.y), angle) for p in SQUARE_CW))
    assert validate_polygon(rotated) == []


def test_too_few_vertices() -> None:
    assert kinds(validate_polygon(points((0, 0), (10, 0)))) == [IssueKind.TOO_FEW_VERTICES]


def test_short_edge_reports_which_edge() -> None:
    issues = validate_polygon(points((0, 0), (100, 0), (100, 100), (0, 100), (0, 99.1)))
    assert kinds(issues) == [IssueKind.SHORT_EDGE]
    assert issues[0].edge_index == 3
    assert issues[0].message == "Edge 4 is 0.90 cm long; edges must be at least 1 cm."


def test_edge_of_exactly_minimum_length_is_allowed() -> None:
    assert validate_polygon(points((0, 0), (100, 0), (100, 1), (100, 100), (0, 100))) == []


def test_collinear_points_have_no_area() -> None:
    assert kinds(validate_polygon(points((0, 0), (50, 0), (100, 0)))) == [IssueKind.NO_AREA]


def test_long_thin_triangle_has_no_area() -> None:
    # Over 1 cm² of area, but nowhere thicker than EPS.
    assert kinds(validate_polygon(points((0, 0), (1000, 0), (500, 0.004)))) == [IssueKind.NO_AREA]


def test_bowtie_is_self_intersecting() -> None:
    bowtie = points((0, 0), (100, 100), (100, 0), (0, 100))
    assert kinds(validate_polygon(bowtie)) == [IssueKind.SELF_INTERSECTION]
