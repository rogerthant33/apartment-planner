"""Graphics items drawn from the document. They are views only: tools do the hit
testing in world coordinates and nothing is ever read back from an item.
"""

import math
from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from apartment_planner.canvas import style
from apartment_planner.geometry.shapes import room_polygon
from apartment_planner.geometry.transform import XY
from apartment_planner.model import Room
from apartment_planner.state.units import Unit, format_area, format_length


def cosmetic_pen(color: QColor, width: float, dashed: bool = False) -> QPen:
    """A pen whose width is in screen pixels, whatever the zoom."""
    pen = QPen(color, width)
    pen.setCosmetic(True)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


class TextLabel(QGraphicsItem):
    """Text centred on its position, at a constant size on screen."""

    PADDING = 2.0

    def __init__(self, text: str, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.text = text
        self._font = QFont()
        self._font.setPointSizeF(9)
        bounds = QFontMetricsF(self._font).boundingRect(
            QRectF(), Qt.AlignmentFlag.AlignCenter, text
        )
        bounds.moveCenter(QPointF(0, 0))
        self._text_rect = bounds
        pad = self.PADDING
        self._rect = bounds.adjusted(-pad, -pad, pad, pad)

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 170))
        painter.drawRoundedRect(self._rect, 2, 2)
        painter.setFont(self._font)
        painter.setPen(style.LABEL)
        painter.drawText(self._text_rect, Qt.AlignmentFlag.AlignCenter, self.text)


class HandleItem(QGraphicsRectItem):
    """A square vertex handle of constant screen size."""

    def __init__(self, point: XY, selected: bool, parent: QGraphicsItem | None = None) -> None:
        half = style.HANDLE_PX / 2
        super().__init__(-half, -half, style.HANDLE_PX, style.HANDLE_PX, parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setPos(*point)
        self.setPen(cosmetic_pen(style.ACCENT, 1.5))
        self.setBrush(style.ACCENT if selected else QColor("white"))
        self.setZValue(2)


class RoomItem(QGraphicsPolygonItem):
    def __init__(
        self,
        room: Room,
        unit: Unit,
        *,
        selected: bool,
        handles: bool,
        selected_vertex: str | None = None,
    ) -> None:
        super().__init__([QPointF(v.x, v.y) for v in room.vertices])
        self.room_id = room.id
        outline = style.ACCENT if selected else style.ROOM_OUTLINE
        self.setPen(cosmetic_pen(outline, style.OUTLINE_PX))
        self.setBrush(QBrush(QColor(room.color) if room.color else style.ROOM_FILL))

        polygon = room_polygon(room)
        anchor = polygon.centroid
        if not polygon.contains(anchor):  # e.g. an L-shaped room
            anchor = polygon.representative_point()
        self.label = TextLabel(f"{room.name}\n{format_area(polygon.area)}", self)
        self.label.setPos(anchor.x, anchor.y)

        self.edge_labels: list[TextLabel] = []
        self.handles: list[HandleItem] = []
        if selected:
            corners = [(v.x, v.y) for v in room.vertices]
            for a, b in zip(corners, [*corners[1:], corners[0]], strict=True):
                label = TextLabel(format_length(math.dist(a, b), unit), self)
                label.setPos((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                self.edge_labels.append(label)
        if handles:
            self.handles = [
                HandleItem((v.x, v.y), v.id == selected_vertex, self) for v in room.vertices
            ]


class PreviewItem(QGraphicsPathItem):
    """What a drag or a drawing tool would produce: red while it isn't valid."""

    def __init__(self) -> None:
        super().__init__()
        self.setZValue(10)
        self.valid = True

    def show_outline(self, points: Sequence[XY], *, closed: bool, valid: bool) -> None:
        path = QPainterPath()
        if points:
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            if closed:
                path.closeSubpath()
        self.valid = valid
        color = style.ACCENT if valid else style.INVALID
        self.setPen(cosmetic_pen(color, style.OUTLINE_PX, dashed=True))
        fill = QColor(color)
        fill.setAlpha(40)
        self.setBrush(fill if closed else Qt.BrushStyle.NoBrush)
        self.setPath(path)
        self.show()

    def clear(self) -> None:
        self.setPath(QPainterPath())
        self.hide()
