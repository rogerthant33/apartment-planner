import pytest

from apartment_planner.geometry import (
    IssueKind,
    PolygonIssue,
    edge_lengths,
    ensure_clockwise,
    signed_area,
    validate_polygon,
)
from apartment_planner.geometry.transform import rotate
from tests.factories import points

# Top-left, top-right, bottom-right, bottom-left: clockwise on screen (y down).
SQUARE_CW = points((0, 0), (100, 0), (100, 100), (0, 100))


def kinds(issues: list[PolygonIssue]) -> list[IssueKind]:
    return [i.kind for i in issues]


def test_signed_area_is_positive_for_clockwise_on_screen() -> None:
    assert signed_area(SQUARE_CW) == pytest.approx(10_000)
    assert signed_area(tuple(reversed(SQUARE_CW))) == pytest.approx(-10_000)


def test_ensure_clockwise_reverses_only_when_needed() -> None:
    assert ensure_clockwise(SQUARE_CW) == SQUARE_CW
    assert ensure_clockwise(tuple(reversed(SQUARE_CW))) == SQUARE_CW


def test_edge_lengths_wrap_around() -> None:
    assert edge_lengths(points((0, 0), (30, 0), (30, 40))) == pytest.approx([30, 40, 50])


def test_valid_square_has_no_issues() -> None:
    assert validate_polygon(SQUARE_CW) == []


def test_valid_concave_l_shape_has_no_issues() -> None:
    l_shape = points((0, 0), (200, 0), (200, 80), (80, 80), (80, 160), (0, 160))
    assert validate_polygon(l_shape) == []


@pytest.mark.parametrize("angle", [0, 90, 37])
def test_rotated_square_is_valid(angle: float) -> None:
    rotated = points(*(rotate((p.x, p.y), angle) for p in SQUARE_CW))
    assert validate_polygon(rotated) == []


def test_too_few_vertices() -> None:
    assert kinds(validate_polygon(points((0, 0), (10, 0)))) == [IssueKind.TOO_FEW_VERTICES]


def test_short_edge_reports_which_edge() -> None:
    issues = validate_polygon(points((0, 0), (100, 0), (100, 0.5), (100, 100), (0, 100)))
    assert kinds(issues) == [IssueKind.SHORT_EDGE]
    assert issues[0].edge_index == 1


def test_duplicate_point_is_a_zero_length_edge() -> None:
    issues = validate_polygon(points((0, 0), (100, 0), (100, 0), (0, 100)))
    assert IssueKind.SHORT_EDGE in kinds(issues)


def test_collinear_points_have_no_area() -> None:
    assert kinds(validate_polygon(points((0, 0), (50, 0), (100, 0)))) == [IssueKind.NO_AREA]


def test_sliver_has_no_area() -> None:
    assert IssueKind.NO_AREA in kinds(
        validate_polygon(points((0, 0), (100, 0), (100, 0.004), (0, 0.004)))
    )


def test_bowtie_is_self_intersecting() -> None:
    bowtie = points((0, 0), (100, 100), (100, 0), (0, 100))
    assert kinds(validate_polygon(bowtie)) == [IssueKind.SELF_INTERSECTION]
