"""The properties panel's fields for furniture and obstacles: their text, and what
typed text changes. Obstacles have no category, clearance or product details.

Pure, so the panel only shows text and commits what `parse_field` returns.
"""

from typing import Any

from apartment_planner.geometry.handles import box_size, with_box_size
from apartment_planner.model import FurnitureItem, FurnitureMeta, Placed
from apartment_planner.state.errors import EditError
from apartment_planner.state.units import Unit, format_length, parse_length

FIELDS: dict[str, str] = {
    "name": "Name",
    "category": "Category",
    "x": "X",
    "y": "Y",
    "rotation": "Rotation",
    "width": "Width",
    "depth": "Depth",
    "clearance": "Clearance",
    "product": "Product",
    "url": "Link",
    "price": "Price",
    "notes": "Notes",
}
"""Field keys and their labels, in the order the panel shows them. The colour is
picked with a button, not typed."""

META_FIELDS = ("product", "url", "price")


def field_values(item: Placed, unit: Unit) -> dict[str, str]:
    """The text each field `item` has. Polygons have no width or depth."""
    values = {
        "name": item.name,
        "x": format_length(item.x, unit),
        "y": format_length(item.y, unit),
        "rotation": f"{item.rotation:g}°",
        "notes": item.notes or "",
    }
    if isinstance(item, FurnitureItem):
        meta = item.meta or FurnitureMeta()
        values |= {
            "category": item.category or "",
            "clearance": "" if item.clearance is None else format_length(item.clearance, unit),
            "product": meta.product or "",
            "url": meta.url or "",
            "price": "" if meta.price is None else f"{meta.price:g}",
        }
    size = box_size(item.shape)
    if size is not None:
        values["width"] = format_length(size[0], unit)
        values["depth"] = format_length(size[1], unit)
    return values


def parse_field(item: Placed, key: str, text: str, unit: Unit) -> dict[str, Any]:
    """The changes to `item` that typing `text` into field `key` means.

    Raises EditError with a message for the user if the text isn't usable.
    """
    text = text.strip()
    label = FIELDS[key]
    match key:
        case "name":
            if not text:
                raise EditError("Enter a name.")
            return {"name": text}
        case "category" | "notes":
            return {key: text or None}
        case "x" | "y":
            return {key: _coordinate(text, unit, label)}
        case "rotation":
            try:
                return {"rotation": float(text.removesuffix("°").replace(",", "."))}
            except ValueError:
                raise EditError(f"{label}: enter an angle in degrees, such as 90.") from None
        case "width" | "depth":
            size = box_size(item.shape)
            if size is None:
                raise EditError(f"{label}: this shape is sized by its corners.")
            length = parse_length(text, unit)
            # parse_length never returns a negative, so `== 0` is the same as `<= 0`.
            if length is None or length <= 0:  # pragma: no mutate
                raise EditError(f"{label}: enter a length greater than 0, such as 120 or 1.2 m.")
            width, depth = {"width": (length, size[1]), "depth": (size[0], length)}[key]
            return {"shape": with_box_size(item.shape, width, depth)}
        case "clearance":
            if not text:
                return {"clearance": None}
            length = parse_length(text, unit)
            if length is None:
                raise EditError(f"{label}: enter a length such as 60, or leave it empty.")
            return {"clearance": length}
        case "price":
            return {"meta": _meta(item, key, _price(text, label))}
        case _:
            return {"meta": _meta(item, key, text or None)}


def _coordinate(text: str, unit: Unit, label: str) -> float:
    negative = text.startswith("-")
    length = parse_length(text.removeprefix("-"), unit)
    if length is None:
        raise EditError(f"{label}: enter a position such as 120 or -1.5 m.")
    return -length if negative else length


def _price(text: str, label: str) -> float | None:
    if not text:
        return None
    try:
        price = float(text.replace(",", "."))
    except ValueError:
        raise EditError(f"{label}: enter an amount such as 499, or leave it empty.") from None
    if price < 0:
        raise EditError(f"{label}: enter an amount of 0 or more.")
    return price


def _meta(item: Placed, key: str, value: str | float | None) -> FurnitureMeta | None:
    assert isinstance(item, FurnitureItem)
    meta = (item.meta or FurnitureMeta()).evolve(**{key: value})
    return None if meta == FurnitureMeta() else meta
