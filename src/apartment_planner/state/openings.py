"""Door, window and opening edits as pure functions. See docs/SPEC.md §5.

Openings always lie on their edge: every edit clamps the offset.
"""

import math
from collections.abc import Iterable
from typing import Any, Literal

from apartment_planner.geometry.openings import edge
from apartment_planner.model import DoorSpec, Opening, ProjectDoc, new_id
from apartment_planner.state.errors import EditError
from apartment_planner.state.rooms import clamp_opening, room
from apartment_planner.state.units import Unit, format_length, parse_length

OpeningKind = Literal["door", "window", "opening"]

DEFAULT_WIDTH: dict[str, float] = {"door": 80.0, "window": 120.0, "opening": 90.0}
DEFAULT_DOOR = DoorSpec(hinge="start", swing="in")
NEW_DOOR_SPEC: dict[str, DoorSpec] = {"door": DEFAULT_DOOR}  # other kinds have none


def opening(doc: ProjectDoc, opening_id: str) -> Opening:
    for candidate in doc.apartment.openings:
        if candidate.id == opening_id:
            return candidate
    raise KeyError(opening_id)


def selected_openings(doc: ProjectDoc, selection: Iterable[str]) -> list[Opening]:
    ids = set(selection)
    return [o for o in doc.apartment.openings if o.id in ids]


def add_opening(
    doc: ProjectDoc, kind: OpeningKind, room_id: str, edge_start_vertex_id: str, offset: float
) -> tuple[ProjectDoc, str]:
    """A new opening of the default width (or the whole wall, if that's shorter)."""
    a, b = edge(room(doc, room_id), edge_start_vertex_id)
    new = Opening(
        id=new_id(),
        kind=kind,
        room_id=room_id,
        edge_start_vertex_id=edge_start_vertex_id,
        # pragma below: the clamp pulls any offset under half the width (at least 40
        # cm, or the opening fills the wall) onto the wall, so a floor of 1 is the same.
        offset=max(offset, 0.0),  # pragma: no mutate
        width=min(DEFAULT_WIDTH[kind], math.dist(a, b)),
        door=NEW_DOOR_SPEC.get(kind),
    )
    new = clamp_opening(new, room(doc, room_id))
    return _with_openings(doc, (*doc.apartment.openings, new)), new.id


def move_opening(
    doc: ProjectDoc, opening_id: str, room_id: str, edge_start_vertex_id: str, offset: float
) -> ProjectDoc:
    """Put an opening somewhere else along a wall, of its own room or another one."""
    return update_opening(
        doc,
        opening_id,
        room_id=room_id,
        edge_start_vertex_id=edge_start_vertex_id,
        offset=max(offset, 0.0),
    )


def update_opening(doc: ProjectDoc, opening_id: str, **changes: Any) -> ProjectDoc:
    """Change an opening. Changing the kind adds or drops the door settings."""
    current = opening(doc, opening_id)
    # "door" sorts before the other kinds, so `<=` is the same.
    is_door = changes.get("kind", current.kind) == "door"  # pragma: no mutate
    if not is_door:
        changes["door"] = None
    elif current.door is None and "door" not in changes:
        changes["door"] = DEFAULT_DOOR
    updated = current.evolve(**changes)
    updated = clamp_opening(updated, room(doc, updated.room_id))
    return _with_openings(
        doc, tuple(updated if o.id == opening_id else o for o in doc.apartment.openings)
    )


def wall_length(doc: ProjectDoc, target: Opening) -> float:
    return math.dist(*edge(room(doc, target.room_id), target.edge_start_vertex_id))


def parse_opening_width(doc: ProjectDoc, target: Opening, text: str, unit: Unit) -> float:
    """The width typed into the opening's width field. It can't be wider than its wall."""
    length = parse_length(text.strip(), unit)
    wall = wall_length(doc, target)
    if not length or length > wall:  # None or 0: parsed lengths are never negative
        raise EditError(
            f"Width: enter a length greater than 0 and at most the wall's "
            f"{format_length(wall, unit)}."
        )
    return length


def parse_opening_offset(text: str, unit: Unit) -> float:
    """The offset typed into the opening's offset field; edits clamp it onto the wall."""
    length = parse_length(text.strip(), unit)
    if length is None:
        raise EditError("Offset: enter the distance from the wall's start, such as 60.")
    return length


def delete_openings(doc: ProjectDoc, ids: Iterable[str]) -> ProjectDoc:
    gone = set(ids)
    return _with_openings(doc, tuple(o for o in doc.apartment.openings if o.id not in gone))


def _with_openings(doc: ProjectDoc, openings: tuple[Opening, ...]) -> ProjectDoc:
    return doc.evolve(apartment=doc.apartment.evolve(openings=openings))
