"""The plan view: zoom, pan, grid, and pointer input for the active tool.

View coordinates become world cm here (`mapToScene`) and nowhere else.
"""

import math

from PySide6.QtCore import QEvent, QLineF, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QNativeGestureEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsView, QWidget
from shapely import unary_union

from apartment_planner.canvas import style
from apartment_planner.canvas.scene import PlanScene
from apartment_planner.canvas.tools import (
    OpeningTool,
    Pointer,
    PolygonTool,
    RectRoomTool,
    SelectTool,
    Tool,
)
from apartment_planner.fit.findings import Finding, check_fit
from apartment_planner.geometry.shapes import placed_polygon, room_polygon
from apartment_planner.model import FurnitureItem, ProjectDoc
from apartment_planner.state.editor import EditorState
from apartment_planner.state.errors import EditError
from apartment_planner.state.openings import delete_openings, selected_openings
from apartment_planner.state.placed import delete_placed, selected_placed
from apartment_planner.state.rooms import delete_selection

MIN_SCALE = 0.02  # screen px per cm: 50 m across a 1000 px window
MAX_SCALE = 40.0
WHEEL_ZOOM = 1.0015  # per 1/8° of wheel rotation
EMPTY_PLAN = QRectF(0, 0, 600, 400)  # what "zoom to fit" shows without rooms


class PlanView(QGraphicsView):
    message = Signal(str)  # something the user should know, e.g. why an edit was refused

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.plan = PlanScene(self)
        self.setScene(self.plan)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._state: EditorState | None = None
        self.editable = False
        self.hidden: frozenset[str] = frozenset()  # furniture hidden from view, not saved
        self._checked: tuple[ProjectDoc | None, list[Finding]] = (None, [])  # doc, findings
        self.tools: dict[str, Tool] = {
            "select": SelectTool(self),
            "rect": RectRoomTool(self),
            "polygon": PolygonTool(self),
            "door": OpeningTool(self, "door"),
            "window": OpeningTool(self, "window"),
            "opening": OpeningTool(self, "opening"),
        }
        self.tool: Tool = self.tools["select"]
        self._pan_from: QPoint | None = None
        self._space_held = False

    # Host protocol for tools

    @property
    def current_state(self) -> EditorState | None:
        return self._state

    @property
    def state(self) -> EditorState:
        if self._state is None:
            raise RuntimeError("No project is open")
        return self._state

    def notify(self, message: str) -> None:
        self.message.emit(message)

    def can_edit_rooms(self) -> bool:
        return (
            self._state is not None
            and self.editable
            and not self._state.doc.settings.apartment_locked
        )

    def delete_selection(self) -> None:
        """Delete the selected furniture, obstacles or openings, or else the selected
        vertex or room."""
        state = self._state
        if state is None or not self.editable:
            return
        placed = selected_placed(state.doc, state.selection)
        openings = selected_openings(state.doc, state.selection)
        furniture_only = all(isinstance(p, FurnitureItem) for p in placed) and not openings
        if not (placed and furniture_only) and not self.can_edit_rooms():
            return
        try:
            if placed:
                doc = delete_placed(state.doc, [p.id for p in placed])
            elif openings:
                doc = delete_openings(state.doc, [o.id for o in openings])
            else:
                doc = delete_selection(state.doc, state.selection)
        except EditError as error:
            self.notify(str(error))
            return
        state.commit(doc)

    def set_hidden(self, ids: frozenset[str]) -> None:
        self.hidden = ids
        if self._state is not None:
            self._state.select(self._state.selection - ids)
        self.refresh()

    # Setup

    def set_state(self, state: EditorState | None, *, editable: bool) -> None:
        self.tool.cancel()
        self._state = state
        self.editable = editable
        if state is None:
            self.plan.clear_plan()
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the scene from the document; call after every change."""
        if self._state is not None:
            self.plan.sync(
                self._state.doc,
                self._state.selection,
                editable=self.editable,
                hidden=self.hidden,
                rotate_offset=style.ROTATE_PX / self.zoom,
                findings=self.findings,
            )

    @property
    def findings(self) -> list[Finding]:
        """Fit-check findings for the active layout, recomputed when the document changes."""
        if self._state is None:
            return []
        doc = self._state.doc
        if doc is not self._checked[0]:
            depth = doc.settings.default_clearance
            self._checked = (doc, check_fit(doc.apartment, doc.active_layout, depth))
        return self._checked[1]

    def set_tool(self, name: str) -> None:
        self.tool.cancel()
        self.tool = self.tools[name]
        self.viewport().setCursor(self.tool.cursor)

    # Zoom and pan never touch the document: they only change the view transform.

    @property
    def zoom(self) -> float:
        """Screen pixels per cm."""
        return self.transform().m11()

    def zoom_by(self, factor: float, anchor: QPoint | None = None) -> None:
        """Zoom keeping the scene point under `anchor` (default: the centre) in place."""
        anchor = anchor if anchor is not None else self.viewport().rect().center()
        factor = min(max(self.zoom * factor, MIN_SCALE), MAX_SCALE) / self.zoom
        fixed = self.mapToScene(anchor)
        self.scale(factor, factor)
        drift = self.mapFromScene(fixed) - anchor
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + drift.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + drift.y())
        self.refresh()  # the rotate handle keeps its distance on screen

    def zoom_to_fit(self) -> None:
        """Show every room and furniture item of the active layout."""
        bounds = EMPTY_PLAN
        if self._state is not None:
            doc = self._state.doc
            shapes = [room_polygon(r) for r in doc.apartment.rooms]
            shapes += [placed_polygon(f) for f in doc.active_layout.furniture]
            if shapes:
                left, top, right, bottom = unary_union(shapes).bounds
                bounds = QRectF(left, top, right - left, bottom - top)
        margin = max(bounds.width(), bounds.height()) * 0.08
        self.fitInView(
            bounds.adjusted(-margin, -margin, margin, margin), Qt.AspectRatioMode.KeepAspectRatio
        )
        self.zoom_by(1.0)  # clamp to the zoom limits

    def pan_by(self, dx: int, dy: int) -> None:
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - dx)
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - dy)

    # Input

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(WHEEL_ZOOM ** event.angleDelta().y(), event.position().toPoint())
            event.accept()
        else:
            super().wheelEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if (
            isinstance(event, QNativeGestureEvent)
            and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture
        ):
            self.zoom_by(1 + event.value(), event.position().toPoint())
            return True
        return super().viewportEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        button = event.button()
        if button == Qt.MouseButton.MiddleButton or (
            button == Qt.MouseButton.LeftButton and self._space_held
        ):
            self._pan_from = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        elif button == Qt.MouseButton.LeftButton and self._state is not None:
            self.tool.press(self._pointer(event))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pan_from is not None:
            position = event.position().toPoint()
            delta = position - self._pan_from
            self._pan_from = position
            self.pan_by(delta.x(), delta.y())
        elif self._state is not None:
            self.tool.move(self._pointer(event))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._pan_from is not None:
            self._pan_from = None
            cursor = Qt.CursorShape.OpenHandCursor if self._space_held else self.tool.cursor
            self.viewport().setCursor(cursor)
        elif event.button() == Qt.MouseButton.LeftButton and self._state is not None:
            self.tool.release(self._pointer(event))

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._state is not None:
            self.tool.double_click(self._pointer(event))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif self._state is None or not self.tool.key(event.key()):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            self.viewport().setCursor(self.tool.cursor)
        else:
            super().keyReleaseEvent(event)

    def _pointer(self, event: QMouseEvent) -> Pointer:
        scene = self.mapToScene(event.position().toPoint())
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        snapping = self.state.doc.settings.snap_enabled and not alt
        return Pointer((scene.x(), scene.y()), 1 / self.zoom, snapping, alt=alt, shift=shift)

    # Grid

    def drawBackground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        rect = QRectF(rect)
        painter.fillRect(rect, style.BACKGROUND)
        minor = self.plan.grid_size
        major = minor * 10
        while major * self.zoom < style.MIN_GRID_PX:
            major *= 10
        if minor * self.zoom >= style.MIN_GRID_PX:
            self._draw_grid(painter, rect, minor, style.GRID_MINOR)
        self._draw_grid(painter, rect, major, style.GRID_MAJOR)

    @staticmethod
    def _draw_grid(painter: QPainter, rect: QRectF, step: float, color: QColor) -> None:
        pen = QPen(color, 0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        x = math.floor(rect.left() / step) * step
        while x <= rect.right():
            painter.drawLine(QLineF(x, rect.top(), x, rect.bottom()))
            x += step
        y = math.floor(rect.top() / step) * step
        while y <= rect.bottom():
            painter.drawLine(QLineF(rect.left(), y, rect.right(), y))
            y += step
