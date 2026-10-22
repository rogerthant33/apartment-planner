"""Furniture and layout edits as pure functions. See docs/SPEC.md §6.

Furniture edits act on the active layout. Groups select and move together:
callers widen a selection with `with_groups` before acting on it.
"""

import math
import re
from collections.abc import Iterable, Sequence
from typing import Any

from apartment_planner.geometry.hits import room_at, room_locator
from apartment_planner.geometry.polygon import edge_lengths, validate_polygon
from apartment_planner.geometry.shapes import placed_polygon
from apartment_planner.geometry.transform import XY, rotate
from apartment_planner.model import (
    FurnitureItem,
    Group,
    Layout,
    Placed,
    Point,
    PolygonShape,
    ProjectDoc,
    Shape,
    new_id,
)
from apartment_planner.state.errors import EditError


def active_furniture(doc: ProjectDoc) -> tuple[FurnitureItem, ...]:
    return doc.active_layout.furniture


def furniture_item(doc: ProjectDoc, item_id: str) -> FurnitureItem:
    for item in active_furniture(doc):
        if item.id == item_id:
            return item
    raise KeyError(item_id)


def selected_furniture(doc: ProjectDoc, selection: Iterable[str]) -> list[FurnitureItem]:
    """Selected furniture of the active layout, in drawing order."""
    ids = set(selection)
    return [item for item in active_furniture(doc) if item.id in ids]


def with_groups(doc: ProjectDoc, ids: Iterable[str]) -> frozenset[str]:
    """`ids` plus every other member of the groups they belong to."""
    chosen = set(ids)
    groups = {item.group_id for item in active_furniture(doc) if item.id in chosen}
    groups.discard(None)
    return frozenset(
        chosen | {item.id for item in active_furniture(doc) if item.group_id in groups}
    )


def name_for(doc: ProjectDoc, base: str, taken: Iterable[str] = ()) -> str:
    """`base` without any number suffix, numbered if the active layout (or `taken`)
    already uses it: "Sofa", "Sofa 2", "Sofa 3"…"""
    names = {item.name for item in active_furniture(doc)} | set(taken)
    base = re.sub(r" \d+$", "", base) or base
    if base not in names:
        return base
    n = 2
    while f"{base} {n}" in names:
        n += 1
    return f"{base} {n}"


def add_furniture(
    doc: ProjectDoc, shape: Shape, at: XY, name: str, category: str | None = None
) -> tuple[ProjectDoc, str]:
    """A new item centred at `at`. Returns its ID."""
    item = FurnitureItem(
        id=new_id(),
        name=name_for(doc, name),
        category=category,
        shape=shape,
        x=at[0],
        y=at[1],
    )
    item = _placed_in_room(doc, item)
    return _with_furniture(doc, (*active_furniture(doc), item)), item.id


def add_polygon_furniture(doc: ProjectDoc, points: Sequence[XY]) -> tuple[ProjectDoc, str]:
    """Custom furniture from a drawn outline in world cm. Its origin is the outline's centre."""
    problem = shape_problem([Point(x=x, y=y) for x, y in points])
    if problem is not None:
        raise EditError(problem)
    xs, ys = [x for x, _ in points], [y for _, y in points]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    shape = PolygonShape(points=tuple(Point(x=x - cx, y=y - cy) for x, y in points))
    return add_furniture(doc, shape, (cx, cy), "Custom shape")


def shape_problem(points: Sequence[Point]) -> str | None:
    """Why `points` can't outline a furniture shape, or None. Either winding is fine."""
    issues = validate_polygon(points)
    return issues[0].message if issues else None


def update_furniture(doc: ProjectDoc, item_id: str, **changes: Any) -> ProjectDoc:
    """Change fields of one item, keeping its room assignment current."""
    item = furniture_item(doc, item_id)
    if item.locked and _moves(changes):
        raise EditError(_locked_message(item))
    updated = _placed_in_room(doc, item.evolve(**changes))
    return _replace(doc, {item.id: updated})


def move_furniture(doc: ProjectDoc, ids: Iterable[str], delta: XY) -> ProjectDoc:
    items = _unlocked(doc, ids)
    dx, dy = delta
    return _replace(
        doc, {i.id: _placed_in_room(doc, i.evolve(x=i.x + dx, y=i.y + dy)) for i in items}
    )


def rotate_furniture(doc: ProjectDoc, ids: Iterable[str], degrees: float) -> ProjectDoc:
    """Turn one item about its origin, or several about the centre of their footprints."""
    items = _unlocked(doc, ids)
    # With no items both branches raise ValueError, so `<=` is the same as `==`.
    if len(items) == 1:  # pragma: no mutate
        (item,) = items
        return _replace(doc, {item.id: item.evolve(rotation=item.rotation + degrees)})
    cx, cy = footprint_centre(items)
    turned = {}
    for item in items:
        ox, oy = rotate((item.x - cx, item.y - cy), degrees)
        moved = item.evolve(x=cx + ox, y=cy + oy, rotation=item.rotation + degrees)
        turned[item.id] = _placed_in_room(doc, moved)
    return _replace(doc, turned)


def footprint_centre(items: Sequence[Placed]) -> XY:
    """Centre of the bounding box around the items' footprints."""
    bounds = [placed_polygon(item).bounds for item in items]
    left, top = min(b[0] for b in bounds), min(b[1] for b in bounds)
    right, bottom = max(b[2] for b in bounds), max(b[3] for b in bounds)
    return ((left + right) / 2, (top + bottom) / 2)


def duplicate_furniture(
    doc: ProjectDoc, ids: Iterable[str], offset: XY
) -> tuple[ProjectDoc, frozenset[str]]:
    """Copies moved by `offset`; copies of a group's members form a new group."""
    return copy_furniture(doc, selected_furniture(doc, ids), doc.active_layout.groups, offset)


def copy_furniture(
    doc: ProjectDoc, items: Sequence[FurnitureItem], groups: Iterable[Group], offset: XY
) -> tuple[ProjectDoc, frozenset[str]]:
    """Copies of `items`, from this or another document, added to the active layout
    and moved by `offset`. Copies of the members of one of `groups` form a new group."""
    group_ids = {item.group_id: new_id() for item in items if item.group_id is not None}
    layout = doc.active_layout
    new_groups = tuple(
        Group(id=group_ids[g.id], name=f"{g.name} copy") for g in groups if g.id in group_ids
    )
    dx, dy = offset
    names: list[str] = []
    for item in items:
        names.append(name_for(doc, item.name, names))
    copies = tuple(
        _placed_in_room(
            doc,
            item.evolve(
                id=new_id(),
                name=name,
                x=item.x + dx,
                y=item.y + dy,
                group_id=_mapped(group_ids, item.group_id),
                locked=False,
            ),
        )
        for item, name in zip(items, names, strict=True)  # pragma: no mutate (one name each)
    )
    layout = layout.evolve(
        furniture=(*layout.furniture, *copies), groups=(*layout.groups, *new_groups)
    )
    return _with_layout(doc, layout), frozenset(c.id for c in copies)


def delete_furniture(doc: ProjectDoc, ids: Iterable[str]) -> ProjectDoc:
    items = _unlocked(doc, ids)
    gone = {item.id for item in items}
    layout = doc.active_layout
    return _with_layout(
        doc,
        _tidy_groups(
            layout.evolve(furniture=tuple(f for f in layout.furniture if f.id not in gone))
        ),
    )


def group_furniture(doc: ProjectDoc, ids: Iterable[str]) -> tuple[ProjectDoc, str]:
    items = selected_furniture(doc, ids)
    if len(items) < 2:
        raise EditError("Select at least two items to group them.")
    layout = doc.active_layout
    numbers = {g.name for g in layout.groups}
    n = 1
    while f"Group {n}" in numbers:
        n += 1
    group = Group(id=new_id(), name=f"Group {n}")
    members = {item.id for item in items}
    layout = layout.evolve(
        furniture=tuple(
            f.evolve(group_id=group.id) if f.id in members else f for f in layout.furniture
        ),
        groups=(*layout.groups, group),
    )
    return _with_layout(doc, _tidy_groups(layout)), group.id


def ungroup_furniture(doc: ProjectDoc, ids: Iterable[str]) -> ProjectDoc:
    members = {item.id for item in selected_furniture(doc, ids)}
    layout = doc.active_layout
    layout = layout.evolve(
        furniture=tuple(f.evolve(group_id=None) if f.id in members else f for f in layout.furniture)
    )
    return _with_layout(doc, _tidy_groups(layout))


def set_locked(doc: ProjectDoc, ids: Iterable[str], locked: bool) -> ProjectDoc:
    return _replace(doc, {i.id: i.evolve(locked=locked) for i in selected_furniture(doc, ids)})


def move_shape_point(doc: ProjectDoc, item_id: str, index: int, world: XY) -> ProjectDoc:
    """Move one corner of a polygon item to a world position."""
    item = furniture_item(doc, item_id)
    assert isinstance(item.shape, PolygonShape)
    lx, ly = rotate((world[0] - item.x, world[1] - item.y), -item.rotation)
    points = list(item.shape.points)
    points[index] = Point(x=lx, y=ly)
    return set_shape_points(doc, item_id, points)


def set_shape_edge_length(doc: ProjectDoc, item_id: str, index: int, length: float) -> ProjectDoc:
    """Make edge `index` of a polygon item `length` cm long by moving its end corner."""
    if not length > 0:
        raise EditError("Enter a length greater than 0.")
    item = furniture_item(doc, item_id)
    assert isinstance(item.shape, PolygonShape)
    points = list(item.shape.points)
    # For an edge index in range, `-` instead of `%` gives a negative index naming the
    # same corner.
    end_index = (index + 1) % len(points)  # pragma: no mutate
    start, end = points[index], points[end_index]
    scale = length / math.hypot(end.x - start.x, end.y - start.y)
    points[end_index] = Point(
        x=start.x + (end.x - start.x) * scale, y=start.y + (end.y - start.y) * scale
    )
    return set_shape_points(doc, item_id, points)


def set_shape_points(doc: ProjectDoc, item_id: str, points: Sequence[Point]) -> ProjectDoc:
    problem = shape_problem(points)
    if problem is not None:
        raise EditError(problem)
    return update_furniture(doc, item_id, shape=PolygonShape(points=tuple(points)))


def shape_edge_lengths(item: FurnitureItem) -> list[float]:
    assert isinstance(item.shape, PolygonShape)
    return edge_lengths(item.shape.points)


# Layouts. Switching layouts is not undoable (see EditorState.update_untracked).


def layout_name_for(doc: ProjectDoc, base: str = "Layout") -> str:
    names = {layout.name for layout in doc.layouts}
    n = 1
    while f"{base} {n}" in names:
        n += 1
    return f"{base} {n}"


def add_layout(doc: ProjectDoc, name: str | None = None) -> tuple[ProjectDoc, str]:
    layout = Layout(id=new_id(), name=_layout_name(doc, name))
    return doc.evolve(layouts=(*doc.layouts, layout)), layout.id


def rename_layout(doc: ProjectDoc, layout_id: str, name: str) -> ProjectDoc:
    name = name.strip()
    if not name:
        raise EditError("Enter a name for the layout.")
    layouts = tuple(
        layout.evolve(name=name) if layout.id == layout_id else layout for layout in doc.layouts
    )
    return doc.evolve(layouts=layouts)


def duplicate_layout(doc: ProjectDoc, layout_id: str) -> tuple[ProjectDoc, str]:
    """A copy with new IDs for the layout, its furniture and its groups."""
    source = doc.layout(layout_id)
    group_ids = {g.id: new_id() for g in source.groups}
    copy = Layout(
        id=new_id(),
        name=_layout_name(doc, f"{source.name} copy"),
        furniture=tuple(
            f.evolve(id=new_id(), group_id=_mapped(group_ids, f.group_id)) for f in source.furniture
        ),
        groups=tuple(g.evolve(id=group_ids[g.id]) for g in source.groups),
    )
    return doc.evolve(layouts=(*doc.layouts, copy)), copy.id


def delete_layout(doc: ProjectDoc, layout_id: str) -> ProjectDoc:
    """Delete a layout; the project keeps at least one. A neighbour becomes active if needed."""
    # A project always has a layout (the model requires one), so `<=` is the same as `==`.
    if len(doc.layouts) == 1:  # pragma: no mutate
        raise EditError("A project needs at least one layout.")
    index = [layout.id for layout in doc.layouts].index(layout_id)
    layouts = tuple(layout for layout in doc.layouts if layout.id != layout_id)
    active = doc.active_layout_id
    if active == layout_id:
        active = layouts[min(index, len(layouts) - 1)].id
    return doc.evolve(layouts=layouts, active_layout_id=active)


def _layout_name(doc: ProjectDoc, name: str | None) -> str:
    if name is None:
        return layout_name_for(doc)
    taken = {layout.name for layout in doc.layouts}
    if name not in taken:
        return name
    n = 2
    while f"{name} {n}" in taken:
        n += 1
    return f"{name} {n}"


# Helpers


def _mapped(ids: dict[str, str], old: str | None) -> str | None:
    return None if old is None else ids[old]


_MOVING_FIELDS = {"x", "y", "rotation", "shape"}


def _moves(changes: dict[str, Any]) -> bool:
    return bool(_MOVING_FIELDS & changes.keys())


def _locked_message(item: FurnitureItem) -> str:
    return f'"{item.name}" is locked. Unlock it (L) to move or resize it.'


def _unlocked(doc: ProjectDoc, ids: Iterable[str]) -> list[FurnitureItem]:
    items = selected_furniture(doc, ids)
    for item in items:
        if item.locked:
            raise EditError(_locked_message(item))
    return items


def _placed_in_room(doc: ProjectDoc, item: FurnitureItem) -> FurnitureItem:
    """`item` with `room_id` naming the room its origin is in, if any."""
    return item.evolve(room_id=room_at(doc.apartment.rooms, (item.x, item.y)))


def reassign_rooms(doc: ProjectDoc, *, unassigned_only: bool = False) -> ProjectDoc:
    """Every item in every layout with `room_id` naming the room its origin is in,
    after the rooms have changed. `unassigned_only`: rooms were only added, so items
    already in a room keep it, even where a new room overlaps it."""
    locate = room_locator(doc.apartment.rooms)

    def placed(item: FurnitureItem) -> FurnitureItem:
        if unassigned_only and item.room_id is not None:
            return item
        room_id = locate((item.x, item.y))
        return item if item.room_id == room_id else item.evolve(room_id=room_id)

    layouts = tuple(
        layout.evolve(furniture=tuple(placed(f) for f in layout.furniture))
        for layout in doc.layouts
    )
    return doc.evolve(layouts=layouts)


def _replace(doc: ProjectDoc, updated: dict[str, FurnitureItem]) -> ProjectDoc:
    layout = doc.active_layout
    furniture = tuple(updated.get(f.id, f) for f in layout.furniture)
    return _with_layout(doc, layout.evolve(furniture=furniture))


def _with_furniture(doc: ProjectDoc, furniture: tuple[FurnitureItem, ...]) -> ProjectDoc:
    return _with_layout(doc, doc.active_layout.evolve(furniture=furniture))


def _with_layout(doc: ProjectDoc, layout: Layout) -> ProjectDoc:
    # `layout` always comes from evolving one of `doc.layouts`, and pydantic keeps the
    # same ID string, so `is` would match exactly when `==` does.
    return doc.evolve(
        layouts=tuple(
            layout if other.id == layout.id else other  # pragma: no mutate
            for other in doc.layouts
        )
    )


def _tidy_groups(layout: Layout) -> Layout:
    """Drop groups with fewer than two members, and the membership of a lone member."""
    counts: dict[str, int] = {}
    for item in layout.furniture:
        if item.group_id is not None:
            counts[item.group_id] = counts.get(item.group_id, 0) + 1
    keep = {group_id for group_id, n in counts.items() if n >= 2}
    return layout.evolve(
        furniture=tuple(
            f.evolve(group_id=None) if f.group_id is not None and f.group_id not in keep else f
            for f in layout.furniture
        ),
        groups=tuple(g for g in layout.groups if g.id in keep),
    )
