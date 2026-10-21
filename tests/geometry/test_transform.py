import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apartment_planner.geometry import local_to_world, rotate, world_to_local

coords = st.floats(min_value=-10_000, max_value=10_000, allow_nan=False)
angles = st.floats(min_value=-720, max_value=720, allow_nan=False)


def assert_close(a: tuple[float, float], b: tuple[float, float], tol: float = 1e-9) -> None:
    assert a[0] == pytest.approx(b[0], abs=tol)
    assert a[1] == pytest.approx(b[1], abs=tol)


def test_positive_rotation_is_clockwise_on_screen() -> None:
    # +x (right) turned 90 degrees clockwise points down, which is +y on screen.
    assert_close(rotate((1, 0), 90), (0, 1))
    assert_close(rotate((0, 1), 90), (-1, 0))


def test_zero_and_full_turns_are_identity() -> None:
    assert_close(rotate((3, 4), 0), (3, 4))
    assert_close(rotate((3, 4), 360), (3, 4))


def test_local_to_world_rotates_then_translates() -> None:
    assert_close(local_to_world((10, 0), (100, 50), 90), (100, 60))


def test_arbitrary_angle() -> None:
    x, y = rotate((10, 0), 37)
    assert x == pytest.approx(10 * math.cos(math.radians(37)))
    assert y == pytest.approx(10 * math.sin(math.radians(37)))


@given(coords, coords, coords, coords, angles)
def test_world_to_local_inverts_local_to_world(
    px: float, py: float, ox: float, oy: float, angle: float
) -> None:
    world = local_to_world((px, py), (ox, oy), angle)
    assert_close(world_to_local(world, (ox, oy), angle), (px, py), tol=1e-6)


@given(coords, coords, angles)
def test_rotation_preserves_distance_from_origin(px: float, py: float, angle: float) -> None:
    rx, ry = rotate((px, py), angle)
    assert math.hypot(rx, ry) == pytest.approx(math.hypot(px, py), abs=1e-6)
