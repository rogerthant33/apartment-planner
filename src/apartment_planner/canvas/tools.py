"""Canvas tools: what pointer gestures do. See docs/SPEC.md §5 and §12.

Tools get pointer positions already mapped to world cm. During a gesture they
only show a preview; on release they compute the result with the pure edit
functions in `state.rooms` and commit it once.
"""

import math
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import Qt

from apartment_planner.canvas import style
from apartment_planner.canvas.scene import PlanScene
from apartment_planner.geometry.hits import edge_at, rect_outline, room_at, vertex_at
from apartment_planner.geometry.snapping import room_targets, snap
from apartment_planner.geometry.transform import XY
from apartment_planner.model import ProjectDoc
from apartment_planner.state.editor import EditorState
from apartment_planner.state.errors import EditError
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


@dataclass(frozen=True)
class Pointer:
    pos: XY  # world cm
    cm_per_px: float  # converts screen distances (tolerances) to world cm
    snapping: bool  # snapping is on and Alt isn't held


class Host(Protocol):
    """What tools need from the canvas."""

    @property
    def state(self) -> EditorState: ...
    @property
    def plan(self) -> PlanScene: ...
    def can_edit_rooms(self) -> bool: ...
    def notify(self, message: str) -> None: ...


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

    def snapped(self, pointer: Pointer, exclude: str | None = None) -> XY:
        if not pointer.snapping:
            return pointer.pos
        doc = self.host.state.doc
        targets = room_targets(doc.apartment.rooms, exclude)
        tolerance = style.SNAP_PX * pointer.cm_per_px
        return snap(pointer.pos, targets, grid=doc.settings.grid_size, tolerance=tolerance).point

    def commit(self, doc: ProjectDoc, select: frozenset[str] | None = None) -> None:
        self.host.state.commit(doc)
        if select is not None:
            self.host.state.select(select)

    def can_edit_rooms(self) -> bool:
        return self.host.can_edit_rooms()


class SelectTool(Tool):
    """Select rooms and vertices; drag vertices; double-click an edge to add a vertex."""

    def __init__(self, host: Host) -> None:
        super().__init__(host)
        self._drag: tuple[str, str] | None = None  # room ID, vertex ID
        self._target: XY | None = None

    def press(self, pointer: Pointer) -> None:
        state = self.host.state
        doc = state.doc
        if doc.settings.apartment_locked:
            state.select(())
            return
        current = selected_room(doc, state.selection)
        if current is not None and self.can_edit_rooms():
            vertex_id = vertex_at(current, pointer.pos, style.HANDLE_PX * pointer.cm_per_px)
            if vertex_id is not None:
                state.select({current.id, vertex_id})
                self._drag, self._target = (current.id, vertex_id), None
                return
        room_id = room_at(doc.apartment.rooms, pointer.pos)
        state.select(() if room_id is None else {room_id})

    def move(self, pointer: Pointer) -> None:
        if self._drag is None:
            return
        room_id, vertex_id = self._drag
        self._target = self.snapped(pointer, exclude=room_id)
        vertices = moved_vertices(room(self.host.state.doc, room_id), vertex_id, self._target)
        self.host.plan.preview.show_outline(
            [(v.x, v.y) for v in vertices], closed=True, valid=outline_problem(vertices) is None
        )

    def release(self, pointer: Pointer) -> None:
        if self._drag is None:
            return
        (room_id, vertex_id), target = self._drag, self._target
        self._drag = self._target = None
        self.host.plan.preview.clear()
        if target is None:  # a click on the handle, not a drag
            return
        try:
            doc = move_vertex(self.host.state.doc, room_id, vertex_id, target)
        except EditError as error:
            self.host.notify(f"{error} The corner went back to where it was.")
            return
        self.commit(doc)

    def double_click(self, pointer: Pointer) -> None:
        if not self.can_edit_rooms():
            return
        doc = self.host.state.doc
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
        self._drag = self._target = None
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
        self.host.plan.preview.show_outline(outline, closed=True, valid=valid)

    def release(self, pointer: Pointer) -> None:
        start, end = self._start, self._end
        self.cancel()
        if start is None or end is None or start == end:
            return  # a click, not a drag
        try:
            doc, room_id = add_room(self.host.state.doc, rect_outline(start, end))
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


class PolygonRoomTool(Tool):
    """Click corners; close on the first corner or with Enter. Escape cancels."""

    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, host: Host) -> None:
        super().__init__(host)
        self.points: list[XY] = []

    def press(self, pointer: Pointer) -> None:
        if not self.can_edit_rooms():
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
        if len(self.points) < 3:
            self.host.notify("Click at least 3 corners before finishing the room.")
            return
        try:
            doc, room_id = add_room(self.host.state.doc, self.points)
        except EditError as error:
            self.host.notify(f"{error} Move or remove a corner (Backspace), or press Escape.")
            return
        self.cancel()
        self.commit(doc, select=frozenset({room_id}))

    def cancel(self) -> None:
        self.points = []
        super().cancel()

    def _show(self, cursor: XY | None) -> None:
        if cursor is None:
            self.host.plan.preview.clear()
            return
        points = [*self.points, cursor] if cursor != self.points[-1] else list(self.points)
        valid = len(points) < 3 or outline_problem(drawn_outline(points)) is None
        self.host.plan.preview.show_outline(points, closed=False, valid=valid)
