import pytest
from hypothesis import given
from hypothesis import strategies as st

from apartment_planner.geometry.transform import local_to_world, rotate, world_to_local

coords = st.floats(min_value=-10_000, max_value=10_000, allow_nan=False)
angles = st.floats(min_value=-720, max_value=720, allow_nan=False)


def test_positive_rotation_is_clockwise_on_screen() -> None:
    # +x (right) turned 90 degrees clockwise points down, which is +y on screen.
    assert rotate((1, 0), 90) == pytest.approx((0, 1))
    assert rotate((0, 1), 90) == pytest.approx((-1, 0))


def test_local_to_world_rotates_then_translates() -> None:
    assert local_to_world((10, 0), (100, 50), 90) == pytest.approx((100, 60))


@given(coords, coords, coords, coords, angles)
def test_world_to_local_inverts_local_to_world(
    px: float, py: float, ox: float, oy: float, angle: float
) -> None:
    world = local_to_world((px, py), (ox, oy), angle)
    assert world_to_local(world, (ox, oy), angle) == pytest.approx((px, py), abs=1e-6)
