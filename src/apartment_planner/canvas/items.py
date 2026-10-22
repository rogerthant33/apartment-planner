"""Graphics items drawn from the document. They are views only: tools do the hit
testing in world coordinates and nothing is ever read back from an item.
"""

import math
from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from apartment_planner.canvas import style
from apartment_planner.fit.findings import Severity
from apartment_planner.geometry.openings import door_swing, edge, inward_normal, opening_span
from apartment_planner.geometry.readouts import Segment
from apartment_planner.geometry.shapes import placed_polygon, room_polygon
from apartment_planner.geometry.transform import XY
from apartment_planner.model import (
    BackgroundImage,
    EllipseShape,
    FurnitureItem,
    Obstacle,
    Opening,
    Placed,
    PolygonShape,
    RectShape,
    Room,
    Shape,
)
from apartment_planner.state.units import Unit, format_area, format_length


def flag_color(flag: Severity | None, default: QColor) -> QColor:
    """Collisions are red and warnings amber (docs/SPEC.md §7)."""
    if flag is None:
        return default
    return style.INVALID if flag == "collision" else style.WARNING


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
        flag: Severity | None = None,
        dimensions: bool = False,
    ) -> None:
        super().__init__([QPointF(v.x, v.y) for v in room.vertices])
        self.room_id = room.id
        self.flag = flag
        outline = style.ACCENT if selected else flag_color(flag, style.ROOM_OUTLINE)
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
        if selected or dimensions:
            corners = [(v.x, v.y) for v in room.vertices]
            for a, b in zip(corners, [*corners[1:], corners[0]], strict=True):
                label = TextLabel(format_length(math.dist(a, b), unit), self)
                label.setPos((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                self.edge_labels.append(label)
        if handles:
            self.handles = [
                HandleItem((v.x, v.y), v.id == selected_vertex, self) for v in room.vertices
            ]


class RotateHandleItem(QGraphicsEllipseItem):
    """The round handle that turns a selected item, of constant screen size."""

    def __init__(self, point: XY) -> None:
        half = style.HANDLE_PX / 2
        super().__init__(-half, -half, style.HANDLE_PX, style.HANDLE_PX)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setPos(*point)
        self.setPen(cosmetic_pen(style.ACCENT, 1.5))
        self.setBrush(QColor("white"))
        self.setZValue(3)


def shape_path(shape: Shape) -> QPainterPath:
    """A shape in its local coordinates; ellipses are drawn as true ellipses."""
    path = QPainterPath()
    match shape:
        case RectShape(width=w, depth=d):
            path.addRect(QRectF(-w / 2, -d / 2, w, d))
        case EllipseShape(rx=rx, ry=ry):
            path.addEllipse(QPointF(0, 0), rx, ry)
        case PolygonShape(points=points):
            path.addPolygon(QPolygonF([QPointF(p.x, p.y) for p in points]))
            path.closeSubpath()
    return path


class PlacedItem(QGraphicsPathItem):
    """A furniture item or obstacle placed at its origin and turned by its rotation.

    Obstacles are hatched and drawn under the furniture.
    """

    def __init__(
        self, item: Placed, unit: Unit, *, selected: bool, flag: Severity | None = None
    ) -> None:
        super().__init__(shape_path(item.shape))
        self.item_id = item.id
        self.flag = flag
        self.setPos(item.x, item.y)
        self.setRotation(item.rotation)
        locked = isinstance(item, FurnitureItem) and item.locked
        obstacle = isinstance(item, Obstacle)
        outline = style.ACCENT if selected else flag_color(flag, style.FURNITURE_OUTLINE)
        width = 1.5 if flag is None else 2.5
        self.setPen(cosmetic_pen(outline, width, dashed=locked))
        if obstacle:
            self.setBrush(
                QBrush(QColor(item.color or style.OBSTACLE_HATCH), Qt.BrushStyle.BDiagPattern)
            )
        else:
            self.setBrush(QBrush(QColor(item.color) if item.color else style.FURNITURE_FILL))
        self.setZValue(0.5 if obstacle else 1)
        self.label = TextLabel(item.name + (" (locked)" if locked else ""), self)
        self.edge_labels: list[TextLabel] = []
        if selected and isinstance(item.shape, PolygonShape):
            corners = [(p.x, p.y) for p in item.shape.points]
            for a, b in zip(corners, [*corners[1:], corners[0]], strict=True):
                label = TextLabel(format_length(math.dist(a, b), unit), self)
                label.setPos((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                self.edge_labels.append(label)


class BackgroundItem(QGraphicsPixmapItem):
    """The floor-plan image under everything, placed and scaled as calibrated."""

    def __init__(self, background: BackgroundImage, pixmap: QPixmap) -> None:
        super().__init__(pixmap)
        self.setPos(background.origin.x, background.origin.y)
        self.setScale(background.cm_per_pixel)
        self.setRotation(background.rotation)
        self.setOpacity(background.opacity)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setZValue(-1)


class ClearanceItem(QGraphicsPathItem):
    """The space an item wants kept free around it, drawn translucent behind it."""

    def __init__(self, item: FurnitureItem) -> None:
        super().__init__()
        assert item.clearance is not None
        zone = placed_polygon(item).buffer(item.clearance)
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in zone.exterior.coords]))
        self.setPath(path)
        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(style.CLEARANCE_FILL)
        self.setZValue(0.3)


class ReadoutItem(QGraphicsLineItem):
    """A measured distance: a dashed line with its length in the middle."""

    def __init__(self, segment: Segment, text: str) -> None:
        (ax, ay), (bx, by) = segment
        super().__init__(ax, ay, bx, by)
        self.setPen(cosmetic_pen(style.ACCENT, 1.0, dashed=True))
        self.setZValue(9)
        self.label = TextLabel(text, self)
        self.label.setPos((ax + bx) / 2, (ay + by) / 2)


class OpeningItem(QGraphicsPathItem):
    """A door, window or plain opening drawn across its wall.

    A gap is cut in the wall line; doors add the leaf and its swing arc,
    windows a double line.
    """

    WINDOW_DEPTH = 8.0  # cm between a window's two lines

    def __init__(self, room: Room, opening: Opening, *, selected: bool) -> None:
        super().__init__()
        self.opening_id = opening.id
        a, b = opening_span(room, opening)
        nx, ny = inward_normal(*edge(room, opening.edge_start_vertex_id))
        color = style.ACCENT if selected else style.ROOM_OUTLINE
        self.setPen(cosmetic_pen(color, 1.5 if selected else 1.2))
        self.setZValue(0.8)
        path = QPainterPath()
        jamb = self.WINDOW_DEPTH / 2
        for end in (a, b):
            path.moveTo(end[0] - nx * jamb, end[1] - ny * jamb)
            path.lineTo(end[0] + nx * jamb, end[1] + ny * jamb)
        if opening.kind == "window":
            for side in (-jamb, jamb):
                path.moveTo(a[0] + nx * side, a[1] + ny * side)
                path.lineTo(b[0] + nx * side, b[1] + ny * side)
        elif opening.kind == "door":
            hinge, *arc = list(door_swing(room, opening).exterior.coords)[:-1]
            path.moveTo(*hinge)
            path.lineTo(*arc[-1])  # the leaf, drawn open
            path.moveTo(*arc[0])
            for point in arc[1:]:
                path.lineTo(*point)
        self.setPath(path)
        gap = QGraphicsLineItem(a[0], a[1], b[0], b[1], self)
        gap.setPen(cosmetic_pen(style.BACKGROUND, style.OUTLINE_PX + 2))
        gap.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent)


class PreviewItem(QGraphicsPathItem):
    """What a drag or a drawing tool would produce: red while it isn't valid."""

    def __init__(self) -> None:
        super().__init__()
        self.setZValue(10)
        self.valid = True
        self._labels: list[TextLabel] = []

    def show_outline(
        self,
        points: Sequence[XY],
        *,
        closed: bool,
        valid: bool,
        labels: Sequence[tuple[XY, str]] = (),
    ) -> None:
        self.show_outlines([points], closed=closed, valid=valid, labels=labels)

    def show_outlines(
        self,
        outlines: Sequence[Sequence[XY]],
        *,
        closed: bool,
        valid: bool,
        labels: Sequence[tuple[XY, str]] = (),
    ) -> None:
        path = QPainterPath()
        for points in outlines:
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
        self._set_labels(labels)
        self.show()

    def clear(self) -> None:
        self.setPath(QPainterPath())
        self._set_labels(())
        self.hide()

    @property
    def label_texts(self) -> list[str]:
        return [label.text for label in self._labels]

    def _set_labels(self, labels: Sequence[tuple[XY, str]]) -> None:
        for label in self._labels:
            scene = label.scene()
            if scene is not None:
                scene.removeItem(label)
        self._labels = []
        for position, text in labels:
            label = TextLabel(text, self)
            label.setPos(*position)
            self._labels.append(label)
