"""Small builders for model objects used across tests."""

from apartment_planner.model import (
    FurnitureItem,
    Point,
    PolygonShape,
    RectShape,
    Room,
    Shape,
    Vertex,
    new_id,
)


def rect_room(x: float, y: float, width: float, depth: float, name: str = "Room") -> Room:
    corners = [(x, y), (x + width, y), (x + width, y + depth), (x, y + depth)]
    return Room(
        id=new_id(),
        name=name,
        vertices=tuple(Vertex(id=new_id(), x=cx, y=cy) for cx, cy in corners),
    )


def item(
    shape: Shape, x: float = 0.0, y: float = 0.0, rotation: float = 0.0, name: str = "Item"
) -> FurnitureItem:
    return FurnitureItem(id=new_id(), name=name, shape=shape, x=x, y=y, rotation=rotation)


def rect_item(
    width: float, depth: float, x: float = 0.0, y: float = 0.0, rotation: float = 0.0
) -> FurnitureItem:
    return item(RectShape(width=width, depth=depth), x, y, rotation)


def points(*coords: tuple[float, float]) -> tuple[Point, ...]:
    return tuple(Point(x=x, y=y) for x, y in coords)


def polygon_shape(*coords: tuple[float, float]) -> PolygonShape:
    return PolygonShape(points=points(*coords))
