import pytest

from apartment_planner.geometry.constants import MIN_EDGE_LENGTH
from apartment_planner.geometry.handles import (
    Handle,
    handle_positions,
    resized,
    rotation_towards,
)
from apartment_planner.model import EllipseShape, RectShape
from tests.factories import item, polygon_shape, rect_item


def test_handles_sit_on_the_box_and_the_rotate_handle_above_it() -> None:
    sofa = rect_item(200, 90, x=300, y=100)

    handles = handle_positions(sofa, rotate_offset=30)

    assert handles[Handle.NW] == (200, 55)
    assert handles[Handle.E] == (400, 100)
    assert handles[Handle.ROTATE] == (300, 25)


@pytest.mark.parametrize(("angle", "rotate_at"), [(90, (375, 100)), (37, None)])
def test_handles_turn_with_the_item(angle: float, rotate_at: tuple[float, float] | None) -> None:
    sofa = rect_item(200, 90, x=300, y=100, rotation=angle)

    handles = handle_positions(sofa, rotate_offset=30)

    if rotate_at is not None:
        assert handles[Handle.ROTATE] == pytest.approx(rotate_at)
    # The rotate handle points the way the top edge faces, whatever the angle.
    assert rotation_towards((300, 100), handles[Handle.ROTATE], snap=False) == pytest.approx(angle)


def test_polygon_rotate_handle_sits_above_its_highest_point() -> None:
    triangle = item(polygon_shape((0, -40), (30, 20), (-30, 20)), x=100, y=100)

    assert handle_positions(triangle, rotate_offset=10) == {Handle.ROTATE: (100, 50)}


def test_corner_drag_keeps_the_opposite_corner() -> None:
    sofa = rect_item(200, 90, x=300, y=100)  # spans x 200..400, y 55..145

    shape, origin = resized(sofa, Handle.SE, (450, 175))

    assert shape == RectShape(width=250, depth=120)
    assert origin == (325, 115)


def test_side_drag_changes_one_dimension_of_a_rotated_item() -> None:
    sofa = rect_item(200, 90, x=300, y=100, rotation=90)  # its local +x points down

    shape, origin = resized(sofa, Handle.E, (310, 250))

    assert shape == RectShape(width=250, depth=90)
    assert origin == pytest.approx((300, 125))


def test_ellipse_resizes_by_its_diameters() -> None:
    table = item(EllipseShape(rx=50, ry=50), x=0, y=0)

    shape, _ = resized(table, Handle.NW, (-70, -30))

    assert shape == EllipseShape(rx=60, ry=40)


def test_dragging_past_the_opposite_side_stops_at_the_minimum_size() -> None:
    sofa = rect_item(200, 90, x=300, y=100)

    shape, origin = resized(sofa, Handle.W, (500, 100))

    assert shape == RectShape(width=MIN_EDGE_LENGTH, depth=90)
    assert origin == (400 - MIN_EDGE_LENGTH / 2, 100)


def test_polygons_have_no_resize_handles() -> None:
    triangle = item(polygon_shape((0, -40), (30, 20), (-30, 20)))

    with pytest.raises(ValueError, match="resize"):
        resized(triangle, Handle.E, (100, 0))


@pytest.mark.parametrize(
    ("point", "snap", "expected"),
    [((0, -10), True, 0), ((10, 0), True, 90), ((10, 10), False, 135), ((-10, -9), True, 315)],
)
def test_rotation_follows_the_pointer_in_15_degree_steps(
    point: tuple[float, float], snap: bool, expected: float
) -> None:
    assert rotation_towards((0, 0), point, snap=snap) == pytest.approx(expected)
