"""Copy, cut and paste: what's on the clipboard, and putting it back into a
document. See docs/SPEC.md §6.

The clipboard keeps copies of model objects, so a paste works after the
originals are gone (cut), in another layout, or in another project.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from apartment_planner.geometry.transform import XY
from apartment_planner.model import (
    FurnitureItem,
    Group,
    Obstacle,
    Opening,
    ProjectDoc,
    Room,
)
from apartment_planner.state import furniture
from apartment_planner.state.placed import copy_obstacles, delete_placed, selected_obstacles
from apartment_planner.state.rooms import copy_rooms, delete_room, selected_rooms


@dataclass(frozen=True)
class Clip:
    """One kind of thing, as a selection holds: furniture (with the groups they
    form), obstacles, or rooms (with their openings)."""

    furniture: tuple[FurnitureItem, ...] = ()
    groups: tuple[Group, ...] = ()
    obstacles: tuple[Obstacle, ...] = ()
    rooms: tuple[Room, ...] = ()
    openings: tuple[Opening, ...] = ()

    @property
    def ids(self) -> frozenset[str]:
        """The copied furniture, obstacles or rooms."""
        placed = (*self.furniture, *self.obstacles)
        return frozenset(p.id for p in placed) | {r.id for r in self.rooms}

    @property
    def is_apartment(self) -> bool:
        """True if pasting it changes the apartment (which must be unlocked)."""
        return bool(self.obstacles or self.rooms)


def copy_selection(doc: ProjectDoc, selection: Iterable[str]) -> Clip | None:
    """What copying the selection puts on the clipboard; None if nothing copyable
    is selected (openings only make sense on their wall)."""
    ids = set(selection)
    items = furniture.selected_furniture(doc, ids)
    if items:
        group_ids = {item.group_id for item in items}
        groups = tuple(g for g in doc.active_layout.groups if g.id in group_ids)
        return Clip(furniture=tuple(items), groups=groups)
    obstacles = selected_obstacles(doc, ids)
    if obstacles:
        return Clip(obstacles=tuple(obstacles))
    rooms = selected_rooms(doc, ids)
    if rooms:
        room_ids = {r.id for r in rooms}
        openings = tuple(o for o in doc.apartment.openings if o.room_id in room_ids)
        return Clip(rooms=tuple(rooms), openings=openings)
    return None


def paste(doc: ProjectDoc, clip: Clip, offset: XY) -> tuple[ProjectDoc, frozenset[str]]:
    """Copies of the clip's contents, moved by `offset`, with new IDs: furniture into
    the active layout (unlocked, numbered names, its groups as new groups), obstacles
    and rooms into the apartment. Returns the document and the copies' IDs."""
    if clip.furniture:
        return furniture.copy_furniture(doc, clip.furniture, clip.groups, offset)
    if clip.obstacles:
        return copy_obstacles(doc, clip.obstacles, offset)
    doc, room_ids = copy_rooms(doc, clip.rooms, clip.openings, offset)
    return doc, frozenset(room_ids)


def remove(doc: ProjectDoc, clip: Clip) -> ProjectDoc:
    """The document without the clip's originals: what a cut leaves behind."""
    for source in clip.rooms:
        doc = delete_room(doc, source.id)
    return delete_placed(doc, clip.ids) if not clip.rooms else doc
