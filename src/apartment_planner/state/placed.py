"""Edits for things placed by shape: furniture (in the active layout) and
obstacles (in the apartment, shared by every layout). See docs/SPEC.md §5, §6.

The canvas and commands call these; each works out which kind it was given.
A selection holds either furniture or obstacles, never both.
"""

from collections.abc import Iterable
from typing import Any

from apartment_planner.geometry.transform import XY, rotate
from apartment_planner.model import Obstacle, Placed, ProjectDoc, Shape, new_id
from apartment_planner.state import furniture
from apartment_planner.state.furniture import footprint_centre


def selected_obstacles(doc: ProjectDoc, selection: Iterable[str]) -> list[Obstacle]:
    ids = set(selection)
    return [o for o in doc.apartment.obstacles if o.id in ids]


def selected_placed(doc: ProjectDoc, selection: Iterable[str]) -> list[Placed]:
    """Selected obstacles if there are any, otherwise selected furniture."""
    ids = set(selection)
    obstacles = selected_obstacles(doc, ids)
    return list(obstacles) if obstacles else list(furniture.selected_furniture(doc, ids))


def obstacle(doc: ProjectDoc, obstacle_id: str) -> Obstacle:
    for candidate in doc.apartment.obstacles:
        if candidate.id == obstacle_id:
            return candidate
    raise KeyError(obstacle_id)


def placed_item(doc: ProjectDoc, item_id: str) -> Placed:
    if is_obstacle(doc, item_id):
        return obstacle(doc, item_id)
    return furniture.furniture_item(doc, item_id)


def is_obstacle(doc: ProjectDoc, item_id: str) -> bool:
    return any(o.id == item_id for o in doc.apartment.obstacles)


def add_obstacle(doc: ProjectDoc, shape: Shape, at: XY, name: str) -> tuple[ProjectDoc, str]:
    names = {o.name for o in doc.apartment.obstacles}
    unique, n = name, 2
    while unique in names:
        unique, n = f"{name} {n}", n + 1
    obstacle = Obstacle(id=new_id(), name=unique, shape=shape, x=at[0], y=at[1])
    return _with_obstacles(doc, (*doc.apartment.obstacles, obstacle)), obstacle.id


def update_placed(doc: ProjectDoc, item_id: str, **changes: Any) -> ProjectDoc:
    if not is_obstacle(doc, item_id):
        return furniture.update_furniture(doc, item_id, **changes)
    return _replace(doc, {item_id: obstacle(doc, item_id).evolve(**changes)})


def move_placed(doc: ProjectDoc, ids: Iterable[str], delta: XY) -> ProjectDoc:
    ids = set(ids)
    obstacles = selected_obstacles(doc, ids)
    if not obstacles:
        return furniture.move_furniture(doc, ids, delta)
    dx, dy = delta
    return _replace(doc, {o.id: o.evolve(x=o.x + dx, y=o.y + dy) for o in obstacles})


def rotate_placed(doc: ProjectDoc, ids: Iterable[str], degrees: float) -> ProjectDoc:
    """Like furniture: one item about its origin, several about their common centre."""
    ids = set(ids)
    obstacles = selected_obstacles(doc, ids)
    if not obstacles:
        return furniture.rotate_furniture(doc, ids, degrees)
    if len(obstacles) == 1:  # pragma: no mutate (never empty here, so `<= 1` is the same)
        (only,) = obstacles
        return _replace(doc, {only.id: only.evolve(rotation=only.rotation + degrees)})
    cx, cy = footprint_centre(obstacles)
    turned = {}
    for o in obstacles:
        ox, oy = rotate((o.x - cx, o.y - cy), degrees)
        turned[o.id] = o.evolve(x=cx + ox, y=cy + oy, rotation=o.rotation + degrees)
    return _replace(doc, turned)


def delete_placed(doc: ProjectDoc, ids: Iterable[str]) -> ProjectDoc:
    ids = set(ids)
    if not selected_obstacles(doc, ids):
        return furniture.delete_furniture(doc, ids)
    return _with_obstacles(doc, tuple(o for o in doc.apartment.obstacles if o.id not in ids))


def duplicate_placed(
    doc: ProjectDoc, ids: Iterable[str], offset: XY
) -> tuple[ProjectDoc, frozenset[str]]:
    ids = set(ids)
    obstacles = selected_obstacles(doc, ids)
    if not obstacles:
        return furniture.duplicate_furniture(doc, ids, offset)
    copies = []
    for o in obstacles:
        doc, copy_id = add_obstacle(doc, o.shape, (o.x + offset[0], o.y + offset[1]), o.name)
        copies.append(copy_id)
        copy = obstacle(doc, copy_id).evolve(rotation=o.rotation, color=o.color, notes=o.notes)
        doc = _replace(doc, {copy_id: copy})
    return doc, frozenset(copies)


def _replace(doc: ProjectDoc, updated: dict[str, Obstacle]) -> ProjectDoc:
    return _with_obstacles(doc, tuple(updated.get(o.id, o) for o in doc.apartment.obstacles))


def _with_obstacles(doc: ProjectDoc, obstacles: tuple[Obstacle, ...]) -> ProjectDoc:
    return doc.evolve(apartment=doc.apartment.evolve(obstacles=obstacles))


def selectable(
    doc: ProjectDoc,
    ids: Iterable[str],
    *,  # pragma: no mutate (`/` still accepts every call that names apartment_editable)
    apartment_editable: bool,
) -> frozenset[str]:
    """What clicking on something that involves `ids` (such as a fit finding) selects.

    Furniture if there is any, otherwise obstacles or rooms while the apartment
    can be edited: a selection holds one kind.
    """
    ids = set(ids)
    furniture_ids = {f.id for f in furniture.selected_furniture(doc, ids)}
    if furniture_ids or not apartment_editable:
        return frozenset(furniture_ids)
    obstacles = {o.id for o in selected_obstacles(doc, ids)}
    return frozenset(obstacles or {r.id for r in doc.apartment.rooms if r.id in ids})
