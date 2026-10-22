"""Fit checks: what's wrong with a layout in an apartment. See docs/SPEC.md §7.

`check_fit` returns findings and never raises on bad geometry: a shape that
isn't a valid polygon becomes a finding itself and is left out of the others.
Findings are informational; nothing is blocked.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

from shapely.geometry import MultiLineString, Polygon
from shapely.ops import unary_union

from apartment_planner.geometry.constants import EPS
from apartment_planner.geometry.openings import door_swing, edge, inward_normal, opening_span
from apartment_planner.geometry.overlap import distance, outside, overlaps
from apartment_planner.geometry.polygon import validate_polygon
from apartment_planner.geometry.shapes import placed_polygon, room_polygon
from apartment_planner.model import (
    Apartment,
    FurnitureItem,
    Layout,
    Obstacle,
    Opening,
    Placed,
    PolygonShape,
    Room,
)

Severity = Literal["collision", "warning"]
Kind = Literal[
    "invalid_shape",
    "overlap",
    "obstacle",
    "outside",
    "door_swing",
    "doorway",
    "clearance",
    "rooms_overlap",
]


@dataclass(frozen=True)
class Finding:
    severity: Severity
    kind: Kind
    ids: tuple[str, ...]  # what's involved: furniture first, then the rest
    message: str


def check_fit(apartment: Apartment, layout: Layout, doorway_depth: float) -> list[Finding]:
    """Every finding for `layout` in `apartment`, collisions first.

    `doorway_depth` is how far in front of a doorway or opening (on both sides
    of the wall) furniture counts as blocking it.
    """
    findings: list[Finding] = []
    furniture = _footprints(layout.furniture, findings)
    obstacles = _footprints(apartment.obstacles, findings)
    floors = _floors(apartment.rooms, findings)
    rooms = {room.id: room for room, _ in floors}
    openings = [o for o in apartment.openings if o.room_id in rooms]
    findings += _overlaps(furniture)
    findings += _obstacle_hits(furniture, obstacles)
    findings += _outside_rooms(furniture, floors)
    swings = [(o, door_swing(rooms[o.room_id], o)) for o in openings if o.door]
    findings += _door_swings(furniture, swings, rooms)
    findings += _doorways(furniture, openings, rooms, doorway_depth, findings)
    findings += _clearances(furniture, obstacles, floors)
    findings += _room_overlaps(floors)
    return sorted(findings, key=lambda f: f.severity != "collision")


type Footprints[T: Placed] = list[tuple[T, Polygon]]


def _footprints[T: Placed](items: Sequence[T], findings: list[Finding]) -> Footprints[T]:
    """Each item's world footprint; invalid shapes become findings instead."""
    valid = []
    for item in items:
        if isinstance(item.shape, PolygonShape):
            issues = validate_polygon(item.shape.points)
            if issues:
                findings.append(
                    Finding(
                        "warning",
                        "invalid_shape",
                        (item.id,),
                        f'"{item.name}" can\'t be checked: {issues[0].message}',
                    )
                )
                continue
        valid.append((item, placed_polygon(item)))
    return valid


def _floors(rooms: Sequence[Room], findings: list[Finding]) -> list[tuple[Room, Polygon]]:
    """Each room's polygon; invalid rooms become findings, and their openings and
    walls are left out of the checks."""
    valid = []
    for room in rooms:
        issues = validate_polygon(room.vertices)
        if issues:
            findings.append(
                Finding(
                    "warning",
                    "invalid_shape",
                    (room.id,),
                    f"{room.name} can't be checked: {issues[0].message}",
                )
            )
        else:
            valid.append((room, room_polygon(room)))
    return valid


def _overlaps(furniture: Footprints[FurnitureItem]) -> Iterator[Finding]:
    for (a, pa), (b, pb) in combinations(furniture, 2):
        if overlaps(pa, pb):
            yield Finding(
                "collision",
                "overlap",
                (a.id, b.id),
                f'"{a.name}" overlaps "{b.name}". Move one of them.',
            )


def _obstacle_hits(
    furniture: Footprints[FurnitureItem], obstacles: Footprints[Obstacle]
) -> Iterator[Finding]:
    for item, footprint in furniture:
        for obstacle, solid in obstacles:
            if overlaps(footprint, solid):
                yield Finding(
                    "collision",
                    "obstacle",
                    (item.id, obstacle.id),
                    f'"{item.name}" overlaps the {obstacle.name.lower()}. Move it.',
                )


def _outside_rooms(
    furniture: Footprints[FurnitureItem], floors: list[tuple[Room, Polygon]]
) -> Iterator[Finding]:
    if not floors:
        return  # nothing drawn yet: no walls to be outside of
    floor = unary_union([polygon for _, polygon in floors])
    for item, footprint in furniture:
        if outside(footprint, floor):
            yield Finding(
                "collision",
                "outside",
                (item.id,),
                f'"{item.name}" crosses a wall or sits outside the rooms.',
            )


def _door_swings(
    furniture: Footprints[FurnitureItem],
    swings: list[tuple[Opening, Polygon]],
    rooms: dict[str, Room],
) -> Iterator[Finding]:
    for item, footprint in furniture:
        for door, swing in swings:
            if overlaps(footprint, swing):
                yield Finding(
                    "collision",
                    "door_swing",
                    (item.id, door.id),
                    f'"{item.name}" is in the way of the door in {rooms[door.room_id].name}.',
                )


def doorway_zone(room: Room, opening: Opening, depth: float) -> Polygon:
    """The area `depth` cm deep on both sides of an opening's span."""
    a, b = opening_span(room, opening)
    nx, ny = inward_normal(*edge(room, opening.edge_start_vertex_id))
    dx, dy = nx * depth, ny * depth
    return Polygon(
        [
            (a[0] - dx, a[1] - dy),
            (b[0] - dx, b[1] - dy),
            (b[0] + dx, b[1] + dy),
            (a[0] + dx, a[1] + dy),
        ]
    )


def _doorways(
    furniture: Footprints[FurnitureItem],
    openings: Sequence[Opening],
    rooms: dict[str, Room],
    depth: float,
    found: list[Finding],
) -> Iterator[Finding]:
    """Furniture in front of a doorway or plain opening (not a window).

    An item already in a door's swing isn't reported again for that door.
    """
    if depth <= 0:
        return
    in_swing = {f.ids for f in found if f.kind == "door_swing"}
    for opening in openings:
        if opening.kind == "window":
            continue
        room = rooms[opening.room_id]
        zone = doorway_zone(room, opening, depth)
        what = "doorway" if opening.kind == "door" else "opening"
        for item, footprint in furniture:
            if (item.id, opening.id) not in in_swing and overlaps(footprint, zone):
                yield Finding(
                    "warning",
                    "doorway",
                    (item.id, opening.id),
                    f'"{item.name}" blocks the {what} in {room.name}.',
                )


def _clearances(
    furniture: Footprints[FurnitureItem],
    obstacles: Footprints[Obstacle],
    floors: list[tuple[Room, Polygon]],
) -> Iterator[Finding]:
    """Items with a clearance set, closer than it to another item or a wall.

    Items that overlap are already collisions, so they aren't reported again.
    Every room edge is a wall, including ones shared with another room.
    """
    walls = MultiLineString([polygon.exterior for _, polygon in floors])
    reported: set[frozenset[str]] = set()
    others: Footprints[Placed] = [*furniture, *obstacles]
    for item, footprint in furniture:
        if item.clearance is None or item.clearance <= 0:
            continue
        limit = item.clearance - EPS
        for other, solid in others:
            pair = frozenset({item.id, other.id})
            if other is item or pair in reported or overlaps(footprint, solid):
                continue
            if distance(footprint, solid) < limit:
                reported.add(pair)
                yield Finding(
                    "warning",
                    "clearance",
                    (item.id, other.id),
                    f'"{other.name}" is within the {item.clearance:g} cm clearance of '
                    f'"{item.name}".',
                )
        if floors and distance(footprint, walls) < limit:
            yield Finding(
                "warning",
                "clearance",
                (item.id,),
                f'A wall is within the {item.clearance:g} cm clearance of "{item.name}".',
            )


def _room_overlaps(floors: list[tuple[Room, Polygon]]) -> Iterator[Finding]:
    for (a, pa), (b, pb) in combinations(floors, 2):
        if overlaps(pa, pb):
            yield Finding(
                "warning",
                "rooms_overlap",
                (a.id, b.id),
                f"{a.name} and {b.name} overlap. Move a corner so they only share walls.",
            )
