"""Small builders for model objects used across tests."""

from datetime import UTC, datetime
from pathlib import Path

from apartment_planner.model import (
    Apartment,
    BackgroundImage,
    DoorSpec,
    EllipseShape,
    FurnitureItem,
    FurnitureMeta,
    Group,
    Layout,
    Obstacle,
    Opening,
    Point,
    PolygonShape,
    ProjectDoc,
    RectShape,
    Room,
    Shape,
    Vertex,
    new_id,
    new_project,
)
from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.files import create_project_file

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


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


def full_project() -> ProjectDoc:
    """A project touching every model type and optional field, with a background image."""
    room = rect_room(0, 0, 400, 300, "Living room").evolve(color="#e8e4dc")
    door = Opening(
        id=new_id(),
        kind="door",
        room_id=room.id,
        edge_start_vertex_id=room.vertices[0].id,
        offset=100,
        width=80,
        door=DoorSpec(hinge="start", swing="in"),
    )
    window = Opening(
        id=new_id(),
        kind="window",
        room_id=room.id,
        edge_start_vertex_id=room.vertices[2].id,
        offset=200,
        width=120,
    )
    column = Obstacle(id=new_id(), name="Column", shape=RectShape(width=30, depth=30), x=385, y=15)
    group = Group(id=new_id(), name="Dining set")
    table = item(EllipseShape(rx=60, ry=60), 200, 150).evolve(group_id=group.id, room_id=room.id)
    sofa = rect_item(200, 90, 100, 50, rotation=90).evolve(
        category="Seating",
        color="#7a8b99",
        notes="Measure the stairwell first",
        locked=True,
        clearance=80,
        meta=FurnitureMeta(product="Söderhamn 3-seat", url="https://example.com/sofa", price=899),
    )
    layout_a = Layout(id=new_id(), name="Sofa by window", furniture=(sofa, table), groups=(group,))
    layout_b = Layout(
        id=new_id(),
        name="L-sofa",
        furniture=(item(polygon_shape((0, 0), (100, 0), (100, 50), (0, 50))),),
    )
    background = BackgroundImage(
        asset_id=new_id(),
        mime_type="image/png",
        origin=Point(x=-20, y=-20),
        cm_per_pixel=2.5,
        rotation=1.5,
    )
    return new_project("Flat", now=NOW).evolve(
        apartment=Apartment(rooms=(room,), openings=(door, window), obstacles=(column,)),
        layouts=(layout_a, layout_b),
        active_layout_id=layout_b.id,
        background=background,
    )


def write_project(path: Path) -> Path:
    """An empty project file named after `path`."""
    create_project_file(path, ProjectFile(new_project(path.name.removesuffix(".apartment"))))
    return path
