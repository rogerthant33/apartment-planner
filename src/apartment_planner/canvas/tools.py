"""Canvas tools: what pointer gestures do. See docs/SPEC.md §5, §6 and §12.

Tools get pointer positions already mapped to world cm. During a gesture they
only show a preview; on release they compute the result with the pure edit
functions in `state` and commit it once.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import Qt

from apartment_planner.canvas import style
from apartment_planner.canvas.scene import PlanScene
from apartment_planner.geometry.handles import Handle, handle_positions, resized, rotation_towards
from apartment_planner.geometry.hits import (
    edge_at,
    nearest_within,
    placed_at,
    placed_in_rect,
    rect_outline,
    room_at,
    shape_corners,
    vertex_at,
)
from apartment_planner.geometry.openings import nearest_edge, opening_at, opening_span
from apartment_planner.geometry.shapes import shape_outline
from apartment_planner.geometry.snapping import (
    placed_edges,
    room_targets,
    snap,
    snap_move,
)
from apartment_planner.geometry.transform import XY, local_to_world_all, world_to_local
from apartment_planner.model import (
    FurnitureItem,
    Obstacle,
    Placed,
    Point,
    PolygonShape,
    ProjectDoc,
)
from apartment_planner.state.background import image_to_world, move_background
from apartment_planner.state.editor import EditorState
from apartment_planner.state.errors import EditError
from apartment_planner.state.furniture import (
    active_furniture,
    add_polygon_furniture,
    move_shape_point,
    shape_problem,
    with_groups,
)
from apartment_planner.state.openings import OpeningKind, add_opening, move_opening
from apartment_planner.state.openings import opening as opening_of
from apartment_planner.state.placed import (
    is_obstacle,
    move_placed,
    placed_item,
    rotate_placed,
    selected_placed,
    update_placed,
)
from apartment_planner.state.rooms import (
    add_room,
    drawn_outline,
    insert_vertex,
    move_vertex,
    moved_vertices,
    outline_problem,
    room,
    selected_room,
)
from apartment_planner.state.units import Unit, format_length


@dataclass(frozen=True)
class Pointer:
    pos: XY  # world cm
    cm_per_px: float  # converts screen distances (tolerances) to world cm
    snapping: bool  # snapping is on and Alt isn't held
    alt: bool = False
    shift: bool = False


class Host(Protocol):
    """What tools need from the canvas."""

    @property
    def state(self) -> EditorState: ...
    @property
    def plan(self) -> PlanScene: ...
    @property
    def editable(self) -> bool: ...
    @property
    def hidden(self) -> frozenset[str]: ...
    def can_edit_rooms(self) -> bool: ...
    def notify(self, message: str) -> None: ...
    def background_size(self) -> tuple[int, int] | None: ...
    def ask_calibration(self, a: XY, b: XY) -> None: ...


def footprint(item: Placed) -> list[XY]:
    return local_to_world_all(shape_outline(item.shape), (item.x, item.y), item.rotation)


def segment_labels(points: Sequence[XY], unit: Unit, closed: bool) -> list[tuple[XY, str]]:
    """Length labels at the middle of each segment, for drawing previews."""
    ends = [*points[1:], points[0]] if closed else points[1:]
    return [
        (((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), format_length(math.dist(a, b), unit))
        for a, b in zip(points, ends, strict=False)
        if a != b
    ]


class Tool:
    cursor = Qt.CursorShape.ArrowCursor

    def __init__(self, host: Host) -> None:
        self.host = host

    def press(self, pointer: Pointer) -> None:
        pass

    def move(self, pointer: Pointer) -> None:
        pass

    def release(self, pointer: Pointer) -> None:
        pass

    def double_click(self, pointer: Pointer) -> None:
        pass

    def key(self, key: int) -> bool:
        """Handle a key press; True if it was used."""
        return False

    def cancel(self) -> None:
        self.host.plan.preview.clear()

    @property
    def doc(self) -> ProjectDoc:
        return self.host.state.doc

    def snapped(self, pointer: Pointer, exclude: str | None = None) -> XY:
        if not pointer.snapping:
            return pointer.pos
        targets = room_targets(self.doc.apartment.rooms, exclude)
        tolerance = style.SNAP_PX * pointer.cm_per_px
        return snap(
            pointer.pos, targets, grid=self.doc.settings.grid_size, tolerance=tolerance
        ).point

    def commit(self, doc: ProjectDoc, select: frozenset[str] | None = None) -> None:
        self.host.state.commit(doc)
        if select is not None:
            self.host.state.select(select)

    def attempt(self, change: Callable[[], ProjectDoc], refused: str = "") -> None:
        """Commit `change()`, or tell the user why it was refused."""
        try:
            doc = change()
        except EditError as error:
            self.host.notify(f"{error}{refused}")
            return
        self.commit(doc)

    def can_edit_rooms(self) -> bool:
        return self.host.can_edit_rooms()

    def visible_furniture(self) -> list[FurnitureItem]:
        hidden = self.host.hidden
        return [item for item in active_furniture(self.doc) if item.id not in hidden]

    def visible_obstacles(self) -> list[Obstacle]:
        return [o for o in self.doc.apartment.obstacles if o.id not in self.host.hidden]


@dataclass
class _Drag:
    kind: str  # "room_vertex", "move", "resize", "rotate", "corner" or "band"
    start: XY
    ids: frozenset[str] = frozenset()
    room_id: str = ""
    vertex_id: str = ""
    handle: Handle | None = None
    corner: int = -1
    result: Callable[[], ProjectDoc] | None = None  # what release commits
    end: XY | None = None


class SelectTool(Tool):
    """Select, move and reshape rooms and furniture; rubber-band select furniture."""

    def __init__(self, host: Host) -> None:
        super().__init__(host)
        self._drag: _Drag | None = None

    def press(self, pointer: Pointer) -> None:
        state, doc, pos = self.host.state, self.doc, pointer.pos
        tolerance = style.HANDLE_PX * pointer.cm_per_px
        chosen = selected_placed(doc, state.selection)
        if self.host.editable and len(chosen) == 1 and self._reshapeable(chosen[0]):
            item = chosen[0]
            handles = handle_positions(item, style.ROTATE_PX * pointer.cm_per_px)
            handle = nearest_within(handles, pos, tolerance)
            if handle is not None:
                kind = "rotate" if handle is Handle.ROTATE else "resize"
                self._drag = _Drag(kind, pos, ids=frozenset({item.id}), handle=handle)
                return
            corners = shape_corners(item) if isinstance(item, FurnitureItem) else {}
            corner = nearest_within(corners, pos, tolerance)
            if corner is not None:
                self._drag = _Drag("corner", pos, ids=frozenset({item.id}), corner=corner)
                return
        if self.can_edit_rooms():
            opening_id = opening_at(
                list(doc.apartment.rooms), list(doc.apartment.openings), pos, tolerance
            )
            if opening_id is not None:
                state.select({opening_id})
                self._drag = _Drag("opening", pos, ids=frozenset({opening_id}))
                return
        current = selected_room(doc, state.selection)
        if current is not None and self.can_edit_rooms():
            vertex_id = vertex_at(current, pos, tolerance)
            if vertex_id is not None:
                state.select({current.id, vertex_id})
                self._drag = _Drag("room_vertex", pos, room_id=current.id, vertex_id=vertex_id)
                return
        hit = placed_at(self.visible_furniture(), pos)
        if hit is None and self.can_edit_rooms():
            hit = placed_at(self.visible_obstacles(), pos)
        if hit is not None:
            self._press_placed(hit, pointer)
            return
        room_id = None if doc.settings.apartment_locked else room_at(doc.apartment.rooms, pos)
        if room_id is not None:
            state.select({room_id})
            return
        if not pointer.shift:
            state.select(())
        self._drag = _Drag("band", pos)

    def _reshapeable(self, item: Placed) -> bool:
        if isinstance(item, FurnitureItem):
            return not item.locked
        return self.can_edit_rooms()

    def _press_placed(self, hit: str, pointer: Pointer) -> None:
        """Select furniture (with its group) or an obstacle, and start moving it.

        A selection holds one kind: Shift+click on the other kind starts afresh.
        """
        state, doc = self.host.state, self.doc
        group = with_groups(doc, {hit})
        obstacle = is_obstacle(doc, hit)
        selected = frozenset(
            i.id
            for i in selected_placed(doc, state.selection)
            if is_obstacle(doc, i.id) == obstacle
        )
        if pointer.shift:
            state.select(selected - group if hit in selected else selected | group)
            return
        if hit not in selected:
            selected = group
            state.select(selected)
        if self.host.editable:
            self._drag = _Drag("move", pointer.pos, ids=with_groups(doc, selected))

    def move(self, pointer: Pointer) -> None:
        drag = self._drag
        if drag is None:
            return
        preview = self.host.plan.preview
        if drag.kind == "band":
            drag.end = pointer.pos
            preview.show_outline(rect_outline(drag.start, pointer.pos), closed=True, valid=True)
        elif drag.kind == "room_vertex":
            target = self.snapped(pointer, exclude=drag.room_id)
            vertices = moved_vertices(room(self.doc, drag.room_id), drag.vertex_id, target)
            drag.result = lambda: move_vertex(self.doc, drag.room_id, drag.vertex_id, target)
            preview.show_outline(
                [(v.x, v.y) for v in vertices], closed=True, valid=outline_problem(vertices) is None
            )
        elif drag.kind == "move":
            self._move_preview(drag, pointer)
        elif drag.kind == "opening":
            self._opening_preview(drag, pointer)
        else:
            self._reshape_preview(drag, pointer)

    def _opening_preview(self, drag: _Drag, pointer: Pointer) -> None:
        (opening_id,) = drag.ids
        found = nearest_edge(
            list(self.doc.apartment.rooms), pointer.pos, style.WALL_PX * pointer.cm_per_px
        )
        if found is None:
            drag.result = None
            self.host.plan.preview.clear()
            return
        target, vertex_id, along = found
        if pointer.snapping:
            along = round(along / self.doc.settings.grid_size) * self.doc.settings.grid_size
        drag.result = lambda: move_opening(self.doc, opening_id, target.id, vertex_id, along)
        moved = opening_of(drag.result(), opening_id)
        span = opening_span(room(self.doc, moved.room_id), moved)
        self.host.plan.preview.show_outline(list(span), closed=False, valid=True)

    def _move_preview(self, drag: _Drag, pointer: Pointer) -> None:
        items = selected_placed(self.doc, drag.ids)
        delta = (pointer.pos[0] - drag.start[0], pointer.pos[1] - drag.start[1])
        if pointer.snapping:
            others = [
                f
                for f in (*self.visible_furniture(), *self.visible_obstacles())
                if f.id not in drag.ids
            ]
            rooms = room_targets(self.doc.apartment.rooms).edges
            corners = [corner for item in items for corner in footprint(item)]
            delta = snap_move(
                corners,
                (items[0].x, items[0].y),
                delta,
                [*rooms, *placed_edges(others)],
                grid=self.doc.settings.grid_size,
                tolerance=style.SNAP_PX * pointer.cm_per_px,
            )
        dx, dy = delta
        outlines = [[(x + dx, y + dy) for x, y in footprint(item)] for item in items]
        valid = not any(getattr(item, "locked", False) for item in items)
        drag.result = lambda: move_placed(self.doc, drag.ids, delta)
        self.host.plan.preview.show_outlines(outlines, closed=True, valid=valid)

    def _reshape_preview(self, drag: _Drag, pointer: Pointer) -> None:
        (item_id,) = drag.ids
        item = placed_item(self.doc, item_id)
        changed: Placed
        if drag.kind == "rotate":
            rotation = rotation_towards((item.x, item.y), pointer.pos, snap=not pointer.alt)
            changed = item.evolve(rotation=rotation)
            drag.result = lambda: rotate_placed(self.doc, drag.ids, rotation - item.rotation)
            valid = True
        elif drag.kind == "resize":
            assert drag.handle is not None
            shape, (x, y) = resized(item, drag.handle, self.snapped(pointer))
            changed = item.evolve(shape=shape, x=x, y=y)
            drag.result = lambda: update_placed(self.doc, item_id, shape=shape, x=x, y=y)
            valid = True
        else:
            target = self.snapped(pointer)
            drag.result = lambda: move_shape_point(self.doc, item_id, drag.corner, target)
            assert isinstance(item.shape, PolygonShape)
            points = list(item.shape.points)
            lx, ly = _local(item, target)
            points[drag.corner] = Point(x=lx, y=ly)
            valid = shape_problem(points) is None
            changed = item.evolve(shape=PolygonShape(points=tuple(points))) if valid else item
            if not valid:
                outline = local_to_world_all(
                    [(p.x, p.y) for p in points], (item.x, item.y), item.rotation
                )
                self.host.plan.preview.show_outline(outline, closed=True, valid=False)
                return
        self.host.plan.preview.show_outline(footprint(changed), closed=True, valid=valid)

    def release(self, pointer: Pointer) -> None:
        drag, self._drag = self._drag, None
        self.host.plan.preview.clear()
        if drag is None:
            return
        if drag.kind == "band":
            if drag.end is not None:
                touched = placed_in_rect(self.visible_furniture(), drag.start, drag.end)
                keep = self.host.state.selection if pointer.shift else frozenset()
                self.host.state.select(keep | with_groups(self.doc, touched))
            return
        if drag.result is None:  # a click, not a drag
            return
        refused = " The corner went back to where it was." if drag.kind == "room_vertex" else ""
        self.attempt(drag.result, refused)

    def double_click(self, pointer: Pointer) -> None:
        if not self.can_edit_rooms():
            return
        doc = self.doc
        tolerance = style.HANDLE_PX * pointer.cm_per_px
        current = selected_room(doc, self.host.state.selection)
        rooms = [current] if current is not None else []
        rooms += [r for r in reversed(doc.apartment.rooms) if r is not current]
        for candidate in rooms:
            edge = edge_at(candidate, pointer.pos, tolerance)
            if edge is not None:
                try:
                    doc, vertex_id = insert_vertex(doc, candidate.id, edge, pointer.pos)
                except EditError as error:
                    self.host.notify(str(error))
                    return
                self.commit(doc, select=frozenset({candidate.id, vertex_id}))
                return

    def key(self, key: int) -> bool:
        if key == Qt.Key.Key_Escape:
            self.cancel()
            self.host.state.select(())
            return True
        return False

    def cancel(self) -> None:
        self._drag = None
        super().cancel()


def _local(item: Placed, world: XY) -> XY:
    return world_to_local(world, (item.x, item.y), item.rotation)


class OpeningTool(Tool):
    """Click near a wall to put a door, window or plain opening there."""

    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, host: Host, kind: OpeningKind) -> None:
        super().__init__(host)
        self.kind: OpeningKind = kind

    def _placement(self, pointer: Pointer) -> Callable[[], tuple[ProjectDoc, str]] | None:
        if not self.can_edit_rooms():
            return None
        found = nearest_edge(
            list(self.doc.apartment.rooms), pointer.pos, style.WALL_PX * pointer.cm_per_px
        )
        if found is None:
            return None
        target, vertex_id, along = found
        if pointer.snapping:
            along = round(along / self.doc.settings.grid_size) * self.doc.settings.grid_size
        return lambda: add_opening(self.doc, self.kind, target.id, vertex_id, along)

    def move(self, pointer: Pointer) -> None:
        place = self._placement(pointer)
        if place is None:
            self.host.plan.preview.clear()
            return
        doc, opening_id = place()
        added = opening_of(doc, opening_id)
        span = opening_span(room(doc, added.room_id), added)
        self.host.plan.preview.show_outline(list(span), closed=False, valid=True)

    def press(self, pointer: Pointer) -> None:
        place = self._placement(pointer)
        if place is None:
            if self.can_edit_rooms():
                self.host.notify(f"Click on a wall to place the {self.kind}.")
            return
        doc, opening_id = place()
        self.cancel()
        self.commit(doc, select=frozenset({opening_id}))


class BackgroundTool(Tool):
    """Drag the background image into place."""

    cursor = Qt.CursorShape.SizeAllCursor

    def __init__(self, host: Host) -> None:
        super().__init__(host)
        self._start: XY | None = None
        self._delta: XY | None = None

    def press(self, pointer: Pointer) -> None:
        bg = self.doc.background
        if bg is None or not self.host.editable:
            return
        if bg.locked:
            self.host.notify("The background image is locked. Unlock it to move it.")
            return
        self._start = pointer.pos

    def move(self, pointer: Pointer) -> None:
        bg, size = self.doc.background, self.host.background_size()
        if self._start is None or bg is None or size is None:
            return
        self._delta = (pointer.pos[0] - self._start[0], pointer.pos[1] - self._start[1])
        w, h = size
        corners = [image_to_world(bg, c) for c in ((0, 0), (w, 0), (w, h), (0, h))]
        dx, dy = self._delta
        moved = [(x + dx, y + dy) for x, y in corners]
        self.host.plan.preview.show_outline(moved, closed=True, valid=True)

    def release(self, pointer: Pointer) -> None:
        delta = self._delta
        self.cancel()
        if delta is not None:
            self.attempt(lambda: move_background(self.doc, delta))

    def cancel(self) -> None:
        self._start = self._delta = None
        super().cancel()


class CalibrateTool(Tool):
    """Click two points on the background image; then the real distance is asked for."""

    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, host: Host) -> None:
        super().__init__(host)
        self._first: XY | None = None

    def press(self, pointer: Pointer) -> None:
        if self.doc.background is None or not self.host.editable:
            return
        if self._first is None:
            self._first = pointer.pos
            return
        first, self._first = self._first, None
        self.cancel()
        self.host.ask_calibration(first, pointer.pos)

    def move(self, pointer: Pointer) -> None:
        if self._first is not None:
            label = format_length(
                math.dist(self._first, pointer.pos), self.doc.settings.display_unit
            )
            middle = ((self._first[0] + pointer.pos[0]) / 2, (self._first[1] + pointer.pos[1]) / 2)
            self.host.plan.preview.show_outline(
                [self._first, pointer.pos], closed=False, valid=True, labels=[(middle, label)]
            )

    def key(self, key: int) -> bool:
        if key == Qt.Key.Key_Escape and self._first is not None:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        self._first = None
        super().cancel()


class RectRoomTool(Tool):
    """Drag out a rectangular room."""

    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, host: Host) -> None:
        super().__init__(host)
        self._start: XY | None = None
        self._end: XY | None = None

    def press(self, pointer: Pointer) -> None:
        if self.can_edit_rooms():
            self._start = self._end = self.snapped(pointer)

    def move(self, pointer: Pointer) -> None:
        if self._start is None:
            return
        self._end = self.snapped(pointer)
        outline = rect_outline(self._start, self._end)
        valid = outline_problem(drawn_outline(outline)) is None
        labels = segment_labels(outline[:3], self.doc.settings.display_unit, closed=False)
        self.host.plan.preview.show_outline(outline, closed=True, valid=valid, labels=labels)

    def release(self, pointer: Pointer) -> None:
        start, end = self._start, self._end
        self.cancel()
        if start is None or end is None or start == end:
            return  # a click, not a drag
        try:
            doc, room_id = add_room(self.doc, rect_outline(start, end))
        except EditError as error:
            self.host.notify(str(error))
            return
        self.commit(doc, select=frozenset({room_id}))

    def key(self, key: int) -> bool:
        if key == Qt.Key.Key_Escape and self._start is not None:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        self._start = self._end = None
        super().cancel()


class PolygonTool(Tool):
    """Click corners; close on the first corner or with Enter. Escape cancels.

    Draws a room while the apartment is unlocked, and a custom furniture shape
    while it is locked.
    """

    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, host: Host) -> None:
        super().__init__(host)
        self.points: list[XY] = []

    @property
    def draws_furniture(self) -> bool:
        return self.doc.settings.apartment_locked

    def press(self, pointer: Pointer) -> None:
        if not (self.host.editable and (self.draws_furniture or self.can_edit_rooms())):
            return
        first_px = (
            math.dist(pointer.pos, self.points[0]) / pointer.cm_per_px if self.points else None
        )
        if len(self.points) >= 3 and first_px is not None and first_px <= style.CLOSE_PX:
            self.finish()
            return
        self.points.append(self.snapped(pointer))
        self._show(self.points[-1])

    def move(self, pointer: Pointer) -> None:
        if self.points:
            self._show(self.snapped(pointer))

    def key(self, key: int) -> bool:
        if not self.points:
            return False
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish()
        elif key == Qt.Key.Key_Escape:
            self.cancel()
        elif key == Qt.Key.Key_Backspace:
            self.points.pop()
            self._show(self.points[-1] if self.points else None)
        else:
            return False
        return True

    def finish(self) -> None:
        what = "shape" if self.draws_furniture else "room"
        if len(self.points) < 3:
            self.host.notify(f"Click at least 3 corners before finishing the {what}.")
            return
        add = add_polygon_furniture if self.draws_furniture else add_room
        try:
            doc, new_id = add(self.doc, self.points)
        except EditError as error:
            self.host.notify(f"{error} Move or remove a corner (Backspace), or press Escape.")
            return
        self.cancel()
        self.commit(doc, select=frozenset({new_id}))

    def cancel(self) -> None:
        self.points = []
        super().cancel()

    def _show(self, cursor: XY | None) -> None:
        if cursor is None:
            self.host.plan.preview.clear()
            return
        points = [*self.points, cursor] if cursor != self.points[-1] else list(self.points)
        if len(points) < 3:
            valid = True
        elif self.draws_furniture:
            valid = shape_problem([Point(x=x, y=y) for x, y in points]) is None
        else:
            valid = outline_problem(drawn_outline(points)) is None
        labels = segment_labels(points, self.doc.settings.display_unit, closed=False)
        self.host.plan.preview.show_outline(points, closed=False, valid=valid, labels=labels)
