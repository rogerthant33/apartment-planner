import math

import pytest

from apartment_planner.geometry.constants import ELLIPSE_SEGMENTS
from apartment_planner.geometry.shapes import l_shape, placed_polygon, room_polygon, shape_outline
from apartment_planner.model import EllipseShape, RectShape
from tests.factories import item, polygon_shape, rect_item, rect_room


def corners(poly: object) -> list[tuple[float, float]]:
    return list(poly.exterior.coords)[:-1]  # type: ignore[attr-defined]


def test_rect_outline_is_centred_on_origin() -> None:
    assert shape_outline(RectShape(width=200, depth=90)) == [
        (-100, -45),
        (100, -45),
        (100, 45),
        (-100, 45),
    ]


def test_placed_rect_rotates_clockwise_about_its_position() -> None:
    poly = placed_polygon(rect_item(200, 90, x=300, y=100, rotation=90))
    assert corners(poly) == [
        pytest.approx((345, 0)),
        pytest.approx((345, 200)),
        pytest.approx((255, 200)),
        pytest.approx((255, 0)),
    ]


def test_ellipse_is_a_regular_polygon_with_the_shared_segment_count() -> None:
    poly = placed_polygon(item(EllipseShape(rx=60, ry=40)))
    n = ELLIPSE_SEGMENTS
    assert len(corners(poly)) == n
    assert poly.bounds == pytest.approx((-60, -40, 60, 40))
    # An inscribed n-gon, stretched to the radii: no skipped or doubled-back points.
    assert poly.area == pytest.approx(n / 2 * math.sin(2 * math.pi / n) * 60 * 40)


def test_polygon_shape_is_offset_by_position() -> None:
    poly = placed_polygon(item(polygon_shape((0, 0), (10, 0), (0, 10)), x=5, y=5))
    assert corners(poly) == [(5, 5), (15, 5), (5, 15)]


def test_room_polygon_uses_vertices_in_order() -> None:
    assert corners(room_polygon(rect_room(0, 0, 400, 300))) == [
        (0, 0),
        (400, 0),
        (400, 300),
        (0, 300),
    ]


def test_l_shape_arm_may_be_thin() -> None:
    assert len(l_shape(width=250, depth=160, arm_width=0.5, arm_depth=0.5).points) == 6


def test_l_shape_area_and_bounds() -> None:
    poly = placed_polygon(item(l_shape(width=255, depth=165, arm_width=90, arm_depth=60)))
    assert poly.bounds == pytest.approx((-127.5, -82.5, 127.5, 82.5))
    assert poly.area == pytest.approx(255 * 60 + 90 * (165 - 60))


@pytest.mark.parametrize(
    ("arm_width", "arm_depth"),
    [(0, 50), (-10, 50), (250, 50), (260, 50), (50, 0), (50, -10), (50, 160), (50, 170)],
)
def test_l_shape_rejects_arm_outside_the_whole(arm_width: float, arm_depth: float) -> None:
    with pytest.raises(ValueError, match="arm"):
        l_shape(width=250, depth=160, arm_width=arm_width, arm_depth=arm_depth)
