import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apartment_planner.geometry import (
    ELLIPSE_SEGMENTS,
    l_shape,
    placed_polygon,
    room_polygon,
    shape_outline,
)
from apartment_planner.model import EllipseShape, RectShape
from tests.factories import item, polygon_shape, rect_item, rect_room


def test_rect_outline_is_centred_on_origin() -> None:
    assert shape_outline(RectShape(width=200, depth=90)) == [
        (-100, -45),
        (100, -45),
        (100, 45),
        (-100, 45),
    ]


def test_placed_rect_unrotated_bounds() -> None:
    poly = placed_polygon(rect_item(200, 90, x=300, y=100))
    assert poly.bounds == pytest.approx((200, 55, 400, 145))


def test_rect_rotated_90_swaps_width_and_depth() -> None:
    minx, miny, maxx, maxy = placed_polygon(rect_item(200, 90, x=0, y=0, rotation=90)).bounds
    assert maxx - minx == pytest.approx(90)
    assert maxy - miny == pytest.approx(200)


def test_rect_rotated_37_keeps_area_and_centre() -> None:
    poly = placed_polygon(rect_item(200, 90, x=50, y=60, rotation=37))
    assert poly.area == pytest.approx(200 * 90)
    assert poly.centroid.x == pytest.approx(50)
    assert poly.centroid.y == pytest.approx(60)


def test_ellipse_uses_shared_segment_count_and_approximates_area() -> None:
    poly = placed_polygon(item(EllipseShape(rx=60, ry=40)))
    assert len(poly.exterior.coords) - 1 == ELLIPSE_SEGMENTS
    assert poly.area == pytest.approx(math.pi * 60 * 40, rel=0.01)


def test_ellipse_rotation_90_swaps_axes() -> None:
    minx, miny, maxx, maxy = placed_polygon(item(EllipseShape(rx=60, ry=40), rotation=90)).bounds
    assert maxx - minx == pytest.approx(80)
    assert maxy - miny == pytest.approx(120)


def test_polygon_shape_is_offset_by_position() -> None:
    poly = placed_polygon(item(polygon_shape((0, 0), (10, 0), (0, 10)), x=5, y=5))
    assert poly.bounds == pytest.approx((5, 5, 15, 15))


def test_room_polygon_uses_vertices_in_order() -> None:
    poly = room_polygon(rect_room(0, 0, 400, 300))
    assert poly.area == pytest.approx(120_000)
    assert list(poly.exterior.coords)[:4] == [(0, 0), (400, 0), (400, 300), (0, 300)]


def test_l_shape_area_and_bounds() -> None:
    shape = l_shape(width=250, depth=160, arm_width=90, arm_depth=90)
    poly = placed_polygon(item(shape))
    assert poly.is_valid
    assert poly.bounds == pytest.approx((-125, -80, 125, 80))
    assert poly.area == pytest.approx(250 * 90 + 90 * (160 - 90))


@pytest.mark.parametrize(("arm_width", "arm_depth"), [(0, 50), (250, 50), (50, 0), (50, 160)])
def test_l_shape_rejects_arm_as_big_as_the_whole(arm_width: float, arm_depth: float) -> None:
    with pytest.raises(ValueError, match="arm"):
        l_shape(width=250, depth=160, arm_width=arm_width, arm_depth=arm_depth)


@given(
    st.floats(min_value=1, max_value=1000),
    st.floats(min_value=1, max_value=1000),
    st.floats(min_value=0, max_value=360),
)
def test_rotation_never_changes_area(width: float, depth: float, rotation: float) -> None:
    poly = placed_polygon(rect_item(width, depth, x=123, y=-45, rotation=rotation))
    assert poly.area == pytest.approx(width * depth, rel=1e-9)
