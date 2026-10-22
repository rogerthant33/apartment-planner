import pytest

from apartment_planner.state.units import (
    Unit,
    describe_distance,
    format_area,
    format_length,
    parse_length,
)


@pytest.mark.parametrize(
    ("cm", "unit", "text"),
    [
        (250, "cm", "250 cm"),
        (250.04, "cm", "250 cm"),
        (250.06, "cm", "250.1 cm"),
        (250, "m", "2.5 m"),
        (1234.56, "m", "12.346 m"),
        (250.06, "mm", "2501 mm"),
    ],
)
def test_format_length_rounds_for_the_unit_without_trailing_zeros(
    cm: float, unit: Unit, text: str
) -> None:
    assert format_length(cm, unit) == text


@pytest.mark.parametrize(
    ("text", "unit", "cm"),
    [
        ("250", "cm", 250),
        ("2.5", "m", 250),
        ("2,5 m", "cm", 250),
        ("2500MM", "m", 250),
        (" 250cm ", "mm", 250),
        (".5", "m", 50),
    ],
)
def test_parse_length_uses_the_display_unit_unless_one_is_given(
    text: str, unit: Unit, cm: float
) -> None:
    assert parse_length(text, unit) == pytest.approx(cm)


@pytest.mark.parametrize("text", ["", "abc", "-5", "2.5 ft", "1.2.3", "5 m m"])
def test_parse_length_rejects_anything_else(text: str) -> None:
    assert parse_length(text, "cm") is None


def test_format_area_in_square_metres() -> None:
    assert format_area(1_234_567) == "123.46 m²"


@pytest.mark.parametrize(
    ("end", "unit", "text"),
    [
        ((300, 400), "cm", "500 cm (300 cm horizontal, 400 cm vertical)"),
        ((-300, -400), "m", "5 m (3 m horizontal, 4 m vertical)"),
        ((300, 0.06), "cm", "300 cm (300 cm horizontal, 0.1 cm vertical)"),
        ((300, 0.04), "cm", "300 cm"),  # the vertical part rounds to nothing
        ((0, -250), "cm", "250 cm"),
    ],
)
def test_distances_give_their_parts_only_when_on_a_slant(
    end: tuple[float, float], unit: Unit, text: str
) -> None:
    assert describe_distance((0, 0), end, unit) == text
