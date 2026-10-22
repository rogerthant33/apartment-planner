"""Door, window and opening edits as pure functions. See docs/SPEC.md §5.

Openings always lie on their edge: every edit clamps the offset.
"""

import math
from collections.abc import Iterable
from typing import Any, Literal

from apartment_planner.geometry.openings import edge
from apartment_planner.model import DoorSpec, Opening, ProjectDoc, new_id
from apartment_planner.state.rooms import clamp_opening, room

OpeningKind = Literal["door", "window", "opening"]

DEFAULT_WIDTH: dict[str, float] = {"door": 80.0, "window": 120.0, "opening": 90.0}
DEFAULT_DOOR = DoorSpec(hinge="start", swing="in")


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
        offset=max(offset, 0.0),
        width=min(DEFAULT_WIDTH[kind], math.dist(a, b)),
        door=DEFAULT_DOOR if kind == "door" else None,
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
    kind = changes.get("kind", current.kind)
    if kind == "door" and current.door is None and "door" not in changes:
        changes["door"] = DEFAULT_DOOR
    elif kind != "door":
        changes["door"] = None
    updated = current.evolve(**changes)
    updated = clamp_opening(updated, room(doc, updated.room_id))
    return _with_openings(
        doc, tuple(updated if o.id == opening_id else o for o in doc.apartment.openings)
    )


def delete_openings(doc: ProjectDoc, ids: Iterable[str]) -> ProjectDoc:
    gone = set(ids)
    return _with_openings(doc, tuple(o for o in doc.apartment.openings if o.id not in gone))


def _with_openings(doc: ProjectDoc, openings: tuple[Opening, ...]) -> ProjectDoc:
    return doc.evolve(apartment=doc.apartment.evolve(openings=openings))
