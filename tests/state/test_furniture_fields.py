from typing import Any

import pytest

from apartment_planner.model import EllipseShape, FurnitureMeta, Obstacle, RectShape
from apartment_planner.state.errors import EditError
from apartment_planner.state.furniture_fields import field_values, parse_field
from tests.factories import item, polygon_shape, rect_item

SOFA = rect_item(200, 90, x=150, y=-20, rotation=90).evolve(
    clearance=60, meta=FurnitureMeta(product="Söderhamn", price=899)
)


def test_values_are_formatted_in_the_display_unit() -> None:
    values = field_values(SOFA, "m")

    assert values["x"] == "1.5 m"
    assert values["y"] == "-0.2 m"
    assert values["rotation"] == "90°"
    assert (values["width"], values["depth"]) == ("2 m", "0.9 m")
    assert (values["clearance"], values["price"], values["url"]) == ("0.6 m", "899", "")


def test_polygons_and_ellipses_show_the_fields_they_have() -> None:
    triangle = item(polygon_shape((0, 0), (10, 0), (0, 10)))
    table = item(EllipseShape(rx=45, ry=30))

    assert "width" not in field_values(triangle, "cm")
    assert field_values(table, "cm")["width"] == "90 cm"


def test_obstacles_have_no_furniture_details() -> None:
    column = Obstacle(id="c", name="Column", shape=RectShape(width=30, depth=30), x=0, y=0)

    assert set(field_values(column, "cm")) == {
        "name",
        "x",
        "y",
        "rotation",
        "width",
        "depth",
        "notes",
    }


@pytest.mark.parametrize(
    ("key", "text", "changes"),
    [
        ("name", " Couch ", {"name": "Couch"}),
        ("notes", "  ", {"notes": None}),
        ("x", "-2.5 m", {"x": -250}),
        ("rotation", "37,5°", {"rotation": 37.5}),
        ("width", "1.8 m", {"shape": RectShape(width=180, depth=90)}),
        ("depth", "100", {"shape": RectShape(width=200, depth=100)}),
        ("clearance", "", {"clearance": None}),
        ("clearance", "0.8 m", {"clearance": 80}),
        ("price", "", {"meta": FurnitureMeta(product="Söderhamn")}),
        (
            "url",
            "https://example.com",
            {"meta": FurnitureMeta(product="Söderhamn", price=899, url="https://example.com")},
        ),
    ],
)
def test_typed_text_becomes_changes(key: str, text: str, changes: dict[str, Any]) -> None:
    assert parse_field(SOFA, key, text, "cm") == changes


def test_clearing_the_last_meta_field_drops_meta() -> None:
    cheap = rect_item(10, 10).evolve(meta=FurnitureMeta(price=5))

    assert parse_field(cheap, "price", "", "cm") == {"meta": None}


@pytest.mark.parametrize(
    ("key", "text", "message"),
    [
        ("name", " ", "Enter a name"),
        ("x", "left", "X: enter a position"),
        ("rotation", "quarter", "Rotation: enter an angle"),
        ("width", "0", "Width: enter a length greater than 0"),
        ("clearance", "lots", "Clearance: enter a length"),
        ("price", "cheap", "Price: enter an amount"),
        ("price", "-5", "Price: enter an amount of 0 or more"),
    ],
)
def test_unusable_text_is_refused_with_a_reason(key: str, text: str, message: str) -> None:
    with pytest.raises(EditError, match=message):
        parse_field(SOFA, key, text, "cm")


def test_polygons_have_no_width() -> None:
    triangle = item(polygon_shape((0, 0), (10, 0), (0, 10)))

    with pytest.raises(EditError, match="sized by its corners"):
        parse_field(triangle, "width", "20", "cm")
