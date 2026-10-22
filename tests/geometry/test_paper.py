import pytest

from apartment_planner.geometry.paper import fits_at, scale_bar_length

A4_AREA = (190.0, 277.0)  # mm inside 10 mm margins, portrait


@pytest.mark.parametrize(
    ("content", "scale", "expected"),
    [
        ((950, 1000), 50, True),  # exactly 190 mm wide
        ((951, 1000), 50, False),
        ((900, 1385), 50, True),  # exactly 277 mm high
        ((900, 1386), 50, False),
    ],
)
def test_fits_at_both_dimensions_inclusive(
    content: tuple[float, float], scale: int, expected: bool
) -> None:
    assert fits_at(content, A4_AREA, scale) is expected


@pytest.mark.parametrize(
    ("longest", "expected"),
    [
        (0.5, 1),
        (1, 1),
        (1.9, 1),
        (2, 2),
        (4.99, 2),
        (5, 5),
        (99, 50),
        (100, 100),
        (250, 200),
        (999.9999999999999, 500),  # log10 of it rounds to exactly 3
    ],
)
def test_scale_bar_length_is_round(longest: float, expected: float) -> None:
    assert scale_bar_length(longest) == expected
