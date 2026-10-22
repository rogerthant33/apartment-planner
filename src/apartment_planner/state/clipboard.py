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
    new_id,
)
from apartment_planner.state import furniture
from apartment_planner.state.placed import add_obstacle, selected_obstacles, update_placed
from apartment_planner.state.rooms import copied_room, selected_rooms


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
    dx, dy = offset
    pasted: list[str] = []
    if clip.furniture:
        group_ids = {g.id: new_id() for g in clip.groups}
        names: list[str] = []
        copies = []
        for item in clip.furniture:
            names.append(furniture.name_for(doc, item.name, names))
            group_id = None if item.group_id is None else group_ids.get(item.group_id)
            copies.append(
                item.evolve(
                    id=new_id(),
                    name=names[-1],
                    x=item.x + dx,
                    y=item.y + dy,
                    group_id=group_id,
                    locked=False,
                )
            )
        groups = tuple(g.evolve(id=group_ids[g.id]) for g in clip.groups)
        layout = doc.active_layout
        layout = layout.evolve(
            furniture=(*layout.furniture, *copies), groups=(*layout.groups, *groups)
        )
        layouts = tuple(layout if lay.id == layout.id else lay for lay in doc.layouts)
        doc = furniture.reassign_rooms(doc.evolve(layouts=layouts))
        pasted += [c.id for c in copies]
    for obstacle in clip.obstacles:
        doc, copy_id = add_obstacle(
            doc, obstacle.shape, (obstacle.x + dx, obstacle.y + dy), obstacle.name
        )
        doc = update_placed(
            doc, copy_id, rotation=obstacle.rotation, color=obstacle.color, notes=obstacle.notes
        )
        pasted.append(copy_id)
    rooms, openings = list(doc.apartment.rooms), list(doc.apartment.openings)
    for source in clip.rooms:
        copy, copied = copied_room(source, clip.openings, offset)
        rooms.append(copy)
        openings.extend(copied)
        pasted.append(copy.id)
    if clip.rooms:
        apartment = doc.apartment.evolve(rooms=tuple(rooms), openings=tuple(openings))
        doc = furniture.reassign_rooms(doc.evolve(apartment=apartment))
    return doc, frozenset(pasted)
