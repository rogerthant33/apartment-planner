"""Persisted project document (schema v1). See docs/SPEC.md §11.

Models are frozen and use tuples, so a document can be shared safely between
undo snapshots. Edits create new instances with `evolve()`.
"""

from collections import Counter
from collections.abc import Iterator
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from apartment_planner.geometry.polygon import is_clockwise

CURRENT_SCHEMA_VERSION = 1

ID = Annotated[str, StringConstraints(min_length=1)]
Name = Annotated[str, StringConstraints(min_length=1)]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Positive = Annotated[float, Field(gt=0)]
NonNegative = Annotated[float, Field(ge=0)]


def _normalise_degrees(value: float) -> float:
    degrees = value % 360.0
    # Tiny negative angles round up to exactly 360. (`%` never exceeds 360, so `==`
    # and `>=` are equivalent here.)
    return 0.0 if degrees == 360.0 else degrees  # pragma: no mutate


Degrees = Annotated[float, AfterValidator(_normalise_degrees)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    def evolve(self, **changes: Any) -> Self:
        """A copy with `changes` applied, re-running this model's validators.

        Use this instead of `model_copy(update=...)`, which skips validation.
        """
        return self.model_validate({**self.__dict__, **changes})


class Point(Model):
    x: float
    y: float


class Vertex(Point):
    id: ID


class ProjectSettings(Model):
    display_unit: Literal["mm", "cm", "m"] = "cm"
    grid_size: Positive = 10.0
    snap_enabled: bool = True
    default_clearance: NonNegative = 60.0  # cm kept free in front of doorways
    apartment_locked: bool = False


class Room(Model):
    id: ID
    name: Name
    # World cm, clockwise on screen (y down). Openings rely on this to know
    # which side of an edge is inside the room.
    vertices: tuple[Vertex, ...] = Field(min_length=3)
    color: Color | None = None

    @model_validator(mode="after")
    def _vertices_clockwise(self) -> Self:
        if not is_clockwise(self.vertices):
            raise ValueError(f"room {self.name!r} has its corners in counter-clockwise order")
        return self


class DoorSpec(Model):
    hinge: Literal["start", "end"]
    swing: Literal["in", "out"]


class Opening(Model):
    id: ID
    kind: Literal["door", "window", "opening"]
    room_id: ID
    # The opening sits on the edge from this vertex to the next one in the room.
    edge_start_vertex_id: ID
    offset: NonNegative  # cm from the edge start to the opening centre
    width: Positive
    door: DoorSpec | None = None

    @model_validator(mode="after")
    def _door_spec_matches_kind(self) -> Self:
        # `kind` is a validated Literal and "door" sorts first, so `is`, `<=` and
        # `is not` mutants behave the same.
        if (self.kind == "door") != (self.door is not None):  # pragma: no mutate
            raise ValueError("door settings must be given for doors and only for doors")
        return self


class RectShape(Model):
    type: Literal["rect"] = "rect"
    width: Positive
    depth: Positive


class EllipseShape(Model):
    type: Literal["ellipse"] = "ellipse"
    rx: Positive
    ry: Positive


class PolygonShape(Model):
    type: Literal["polygon"] = "polygon"
    points: tuple[Point, ...] = Field(min_length=3)


Shape = Annotated[RectShape | EllipseShape | PolygonShape, Field(discriminator="type")]


class Placed(Model):
    id: ID
    name: Name
    shape: Shape
    x: float  # world position of the shape's local origin
    y: float
    rotation: Degrees = 0.0  # clockwise
    color: Color | None = None
    notes: str | None = None


class Obstacle(Placed):
    pass


class FurnitureMeta(Model):
    product: str | None = None
    url: str | None = None
    price: NonNegative | None = None


class FurnitureItem(Placed):
    category: str | None = None
    room_id: ID | None = None
    locked: bool = False
    group_id: ID | None = None
    clearance: NonNegative | None = None  # cm kept free around it; None: no zone
    meta: FurnitureMeta | None = None


class Group(Model):
    id: ID
    name: Name


class Layout(Model):
    id: ID
    name: Name
    furniture: tuple[FurnitureItem, ...] = ()
    groups: tuple[Group, ...] = ()


class Apartment(Model):
    rooms: tuple[Room, ...] = ()
    openings: tuple[Opening, ...] = ()
    obstacles: tuple[Obstacle, ...] = ()


class BackgroundImage(Model):
    asset_id: ID
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    origin: Point  # world position of the image's top-left corner
    cm_per_pixel: Positive
    rotation: Degrees = 0.0
    opacity: Annotated[float, Field(ge=0, le=1)] = 0.5
    visible: bool = True
    locked: bool = True


class ProjectDoc(Model):
    id: ID
    name: Name
    created_at: AwareDatetime
    updated_at: AwareDatetime
    settings: ProjectSettings = ProjectSettings()
    apartment: Apartment = Apartment()
    layouts: tuple[Layout, ...] = Field(min_length=1)
    active_layout_id: ID
    background: BackgroundImage | None = None

    def layout(self, layout_id: str) -> Layout:
        for layout in self.layouts:
            if layout.id == layout_id:
                return layout
        raise KeyError(layout_id)

    @property
    def active_layout(self) -> Layout:
        return self.layout(self.active_layout_id)

    def all_ids(self) -> Iterator[str]:
        """Every entity ID in the document (not the project ID itself)."""
        for room in self.apartment.rooms:
            yield room.id
            yield from (v.id for v in room.vertices)
        yield from (o.id for o in self.apartment.openings)
        yield from (o.id for o in self.apartment.obstacles)
        for layout in self.layouts:
            yield layout.id
            yield from (f.id for f in layout.furniture)
            yield from (g.id for g in layout.groups)
        if self.background is not None:
            yield self.background.asset_id

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        problems = _reference_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def _reference_problems(doc: ProjectDoc) -> list[str]:
    problems: list[str] = []

    # Counts are at least 1, so `> 1` and `!= 1` are equivalent.
    duplicates = sorted(i for i, n in Counter(doc.all_ids()).items() if n > 1)  # pragma: no mutate
    if duplicates:
        problems.append(f"duplicate IDs: {', '.join(duplicates)}")

    if doc.active_layout_id not in {layout.id for layout in doc.layouts}:
        problems.append(f"active_layout_id {doc.active_layout_id!r} is not a layout")

    rooms = {room.id: room for room in doc.apartment.rooms}
    for i, opening in enumerate(doc.apartment.openings):
        where = f"apartment.openings[{i}]"
        room = rooms.get(opening.room_id)
        if room is None:
            problems.append(f"{where}.room_id {opening.room_id!r} is not a room")
        elif opening.edge_start_vertex_id not in {v.id for v in room.vertices}:
            problems.append(
                f"{where}.edge_start_vertex_id {opening.edge_start_vertex_id!r} "
                f"is not a vertex of room {room.name!r}"
            )

    for li, layout in enumerate(doc.layouts):
        group_ids = {g.id for g in layout.groups}
        for fi, item in enumerate(layout.furniture):
            where = f"layouts[{li}].furniture[{fi}]"
            if item.group_id is not None and item.group_id not in group_ids:
                problems.append(f"{where}.group_id {item.group_id!r} is not a group in its layout")
            if item.room_id is not None and item.room_id not in rooms:
                problems.append(f"{where}.room_id {item.room_id!r} is not a room")

    return problems
