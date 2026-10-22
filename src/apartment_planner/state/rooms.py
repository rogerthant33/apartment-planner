"""Room edits as pure functions: a document in, a new document out. See docs/SPEC.md §5.

Edits that would leave a room invalid raise `EditError` with a message for the
user, so the canvas can revert and say why.
"""

import math
from collections.abc import Callable, Iterable, Sequence

from apartment_planner.geometry.hits import room_at
from apartment_planner.geometry.polygon import is_clockwise, signed_area, validate_polygon
from apartment_planner.geometry.transform import XY
from apartment_planner.model import Opening, Point, ProjectDoc, Room, Vertex, new_id
from apartment_planner.state.errors import EditError

MIN_VERTICES = 3


def outline_problem(points: Sequence[Point]) -> str | None:
    """Why `points` (clockwise on screen) can't be a room outline, or None."""
    issues = validate_polygon(points)
    if issues:
        return issues[0].message
    if not is_clockwise(points):
        return "That would turn the room inside out. Move the corner back across the opposite wall."
    return None


def drawn_outline(points: Sequence[XY]) -> list[Point]:
    """A freshly drawn outline in either winding, turned clockwise on screen."""
    outline = [Point(x=x, y=y) for x, y in points]
    if signed_area(outline) < 0:
        outline.reverse()
    return outline


def with_default_lock(doc: ProjectDoc) -> ProjectDoc:
    """Projects that have rooms open with the apartment locked (docs/SPEC.md §5)."""
    if doc.apartment.rooms and not doc.settings.apartment_locked:
        return doc.evolve(settings=doc.settings.evolve(apartment_locked=True))
    return doc


def room(doc: ProjectDoc, room_id: str) -> Room:
    for candidate in doc.apartment.rooms:
        if candidate.id == room_id:
            return candidate
    raise KeyError(room_id)


def room_name_for(doc: ProjectDoc) -> str:
    """The first of "Room 1", "Room 2", … that no room uses yet."""
    names = {r.name for r in doc.apartment.rooms}
    n = 1
    while f"Room {n}" in names:
        n += 1
    return f"Room {n}"


def add_room(
    doc: ProjectDoc, points: Sequence[XY], name: str | None = None
) -> tuple[ProjectDoc, str]:
    """Add a room with the given outline in either winding. Returns the new room's ID."""
    outline = drawn_outline(points)
    _check(outline)
    new = Room(
        id=new_id(),
        name=name or room_name_for(doc),
        vertices=tuple(Vertex(id=new_id(), x=p.x, y=p.y) for p in outline),
    )
    return _with_rooms(doc, (*doc.apartment.rooms, new)), new.id


def rename_room(doc: ProjectDoc, room_id: str, name: str) -> ProjectDoc:
    name = name.strip()
    if not name:
        raise EditError("Enter a name for the room.")
    updated = room(doc, room_id).evolve(name=name)
    return _with_rooms(doc, (updated if r.id == room_id else r for r in doc.apartment.rooms))


def recolour_room(doc: ProjectDoc, room_id: str, color: str | None) -> ProjectDoc:
    """Fill the room with `color` (#rrggbb), or the default fill for None."""
    changed = room(doc, room_id).evolve(color=color)
    return _with_rooms(doc, [changed if r.id == room_id else r for r in doc.apartment.rooms])


def delete_room(doc: ProjectDoc, room_id: str) -> ProjectDoc:
    """Remove a room with its openings. Furniture placed in it no longer names a room."""
    apartment = doc.apartment.evolve(
        rooms=tuple(r for r in doc.apartment.rooms if r.id != room_id),
        openings=tuple(o for o in doc.apartment.openings if o.room_id != room_id),
    )
    layouts = tuple(
        layout.evolve(
            furniture=tuple(
                f.evolve(room_id=None) if f.room_id == room_id else f for f in layout.furniture
            )
        )
        for layout in doc.layouts
    )
    return doc.evolve(apartment=apartment, layouts=layouts)


def duplicate_room(doc: ProjectDoc, room_id: str, offset: XY) -> tuple[ProjectDoc, str]:
    """A copy of the room and its openings, moved by `offset`. Returns the copy's ID."""
    source = room(doc, room_id)
    vertex_ids = {v.id: new_id() for v in source.vertices}
    dx, dy = offset
    copy = source.evolve(
        id=new_id(),
        name=f"{source.name} copy",
        vertices=tuple(
            Vertex(id=vertex_ids[v.id], x=v.x + dx, y=v.y + dy) for v in source.vertices
        ),
    )
    openings = tuple(
        o.evolve(
            id=new_id(), room_id=copy.id, edge_start_vertex_id=vertex_ids[o.edge_start_vertex_id]
        )
        for o in doc.apartment.openings
        if o.room_id == room_id
    )
    apartment = doc.apartment.evolve(
        rooms=(*doc.apartment.rooms, copy), openings=(*doc.apartment.openings, *openings)
    )
    return doc.evolve(apartment=apartment), copy.id


def selected_room(doc: ProjectDoc, selection: frozenset[str]) -> Room | None:
    """The selected room, or the room of the selected vertex."""
    for candidate in doc.apartment.rooms:
        if candidate.id in selection or any(v.id in selection for v in candidate.vertices):
            return candidate
    return None


def selected_rooms(doc: ProjectDoc, selection: Iterable[str]) -> list[Room]:
    ids = set(selection)
    return [r for r in doc.apartment.rooms if r.id in ids]


def move_rooms(doc: ProjectDoc, ids: Iterable[str], delta: XY) -> ProjectDoc:
    """Move whole rooms. Their openings go with them; furniture stays put but is
    reassigned to whichever room it now stands in."""
    ids, (dx, dy) = set(ids), delta
    rooms = [
        r.evolve(vertices=tuple(v.evolve(x=v.x + dx, y=v.y + dy) for v in r.vertices))
        if r.id in ids
        else r
        for r in doc.apartment.rooms
    ]
    doc = _with_rooms(doc, rooms)
    layouts = tuple(
        layout.evolve(
            furniture=tuple(
                f.evolve(room_id=room_at(doc.apartment.rooms, (f.x, f.y))) for f in layout.furniture
            )
        )
        for layout in doc.layouts
    )
    return doc.evolve(layouts=layouts)


def delete_selection(doc: ProjectDoc, selection: frozenset[str]) -> ProjectDoc:
    """Delete the selected vertex if there is one, otherwise the selected rooms."""
    for candidate in doc.apartment.rooms:
        for vertex in candidate.vertices:
            if vertex.id in selection:
                return delete_vertex(doc, candidate.id, vertex.id)
    for room_id in [r.id for r in doc.apartment.rooms if r.id in selection]:
        doc = delete_room(doc, room_id)
    return doc


def moved_vertices(target: Room, vertex_id: str, point: XY) -> tuple[Vertex, ...]:
    """The room's vertices with one of them moved; for previews before committing."""
    x, y = point
    return tuple(v.evolve(x=x, y=y) if v.id == vertex_id else v for v in target.vertices)


def move_vertex(doc: ProjectDoc, room_id: str, vertex_id: str, point: XY) -> ProjectDoc:
    return set_outline(doc, room_id, moved_vertices(room(doc, room_id), vertex_id, point))


def set_edge_length(doc: ProjectDoc, room_id: str, vertex_id: str, length: float) -> ProjectDoc:
    """Make the edge starting at `vertex_id` `length` cm long by moving its end vertex
    along the edge's direction."""
    if not length > 0:
        raise EditError("Enter a length greater than 0.")
    target = room(doc, room_id)
    i = _index(target, vertex_id)
    start, end = target.vertices[i], _next(target, i)
    scale = length / _length(start, end)
    point = (start.x + (end.x - start.x) * scale, start.y + (end.y - start.y) * scale)
    return move_vertex(doc, room_id, end.id, point)


def insert_vertex(
    doc: ProjectDoc, room_id: str, edge_start_vertex_id: str, point: XY
) -> tuple[ProjectDoc, str]:
    """Split an edge at the point on it nearest to `point`. Returns the new vertex's ID.

    Openings past the split move to the new edge and keep their place on the wall.
    """
    target = room(doc, room_id)
    i = _index(target, edge_start_vertex_id)
    start, end = target.vertices[i], _next(target, i)
    t = _projection(point, start, end)
    vertex = Vertex(
        id=new_id(), x=start.x + (end.x - start.x) * t, y=start.y + (end.y - start.y) * t
    )
    split = t * _length(start, end)
    vertices = (*target.vertices[: i + 1], vertex, *target.vertices[i + 1 :])

    def reattach(opening: Opening) -> Opening:
        if opening.edge_start_vertex_id == start.id and opening.offset > split:
            return opening.evolve(edge_start_vertex_id=vertex.id, offset=opening.offset - split)
        return opening

    return set_outline(doc, room_id, vertices, reattach), vertex.id


def delete_vertex(doc: ProjectDoc, room_id: str, vertex_id: str) -> ProjectDoc:
    """Remove a corner, merging its two edges. Openings on the removed edge move to the
    merged edge, as close to where they were as possible."""
    target = room(doc, room_id)
    if len(target.vertices) <= MIN_VERTICES:
        raise EditError(f"A room needs at least {MIN_VERTICES} corners.")
    i = _index(target, vertex_id)
    previous, removed, following = target.vertices[i - 1], target.vertices[i], _next(target, i)

    def reattach(opening: Opening) -> Opening:
        if opening.edge_start_vertex_id != vertex_id:
            return opening
        t = opening.offset / _length(removed, following)
        centre = (
            removed.x + (following.x - removed.x) * t,
            removed.y + (following.y - removed.y) * t,
        )
        offset = _projection(centre, previous, following) * _length(previous, following)
        return opening.evolve(edge_start_vertex_id=previous.id, offset=offset)

    remaining = tuple(v for v in target.vertices if v.id != vertex_id)
    return set_outline(doc, room_id, remaining, reattach)


def set_outline(
    doc: ProjectDoc,
    room_id: str,
    vertices: Sequence[Vertex],
    reattach: Callable[[Opening], Opening] = lambda opening: opening,
) -> ProjectDoc:
    """Replace a room's vertices, keeping its openings on their edges.

    `reattach` first moves openings whose edge changes; it runs in the same
    step, since an opening may only name a vertex its room has.
    """
    _check(vertices)
    updated = room(doc, room_id).evolve(vertices=tuple(vertices))
    apartment = doc.apartment.evolve(
        rooms=tuple(updated if r.id == room_id else r for r in doc.apartment.rooms),
        openings=tuple(
            clamp_opening(reattach(o), updated) if o.room_id == room_id else o
            for o in doc.apartment.openings
        ),
    )
    return doc.evolve(apartment=apartment)


def clamp_opening(opening: Opening, target: Room) -> Opening:
    """The opening moved along its edge just enough to lie on it."""
    i = _index(target, opening.edge_start_vertex_id)
    length = _length(target.vertices[i], _next(target, i))
    half = opening.width / 2
    offset = (
        # pragma: at width == length both branches give length / 2.
        length / 2
        if opening.width >= length
        else min(max(opening.offset, half), length - half)  # pragma: no mutate
    )
    return opening if offset == opening.offset else opening.evolve(offset=offset)


def _check(points: Sequence[Point]) -> None:
    problem = outline_problem(points)
    if problem is not None:
        raise EditError(problem)


def _with_rooms(doc: ProjectDoc, rooms: Iterable[Room]) -> ProjectDoc:
    return doc.evolve(apartment=doc.apartment.evolve(rooms=tuple(rooms)))


def _index(target: Room, vertex_id: str) -> int:
    for i, vertex in enumerate(target.vertices):
        if vertex.id == vertex_id:
            return i
    raise KeyError(vertex_id)


def _next(target: Room, i: int) -> Vertex:
    # `- len` instead of `%` would index the same vertex from the end.
    return target.vertices[(i + 1) % len(target.vertices)]  # pragma: no mutate


def _length(a: Point, b: Point) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _projection(point: XY, start: Point, end: Point) -> float:
    """Where `point` projects onto the segment, from 0 (start) to 1 (end)."""
    dx, dy = end.x - start.x, end.y - start.y
    t = ((point[0] - start.x) * dx + (point[1] - start.y) * dy) / (dx * dx + dy * dy)
    return min(max(t, 0.0), 1.0)
