"""Small toolbar icons, drawn in code so they follow the theme's text colour."""

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

SIZE = 32  # drawn at twice the usual toolbar size, for sharp HiDPI screens

Painter = Callable[[QPainter], None]


def _icon(draw: Painter, colour: QColor) -> QPixmap:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(colour, 2.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    draw(painter)
    painter.end()
    return pixmap


def _padlock(painter: QPainter, open_: bool) -> None:
    shackle = QPainterPath()
    if open_:  # raised, its left leg out of the body
        shackle.moveTo(22, 15)
        shackle.lineTo(22, 7)
        shackle.arcTo(QRectF(10, 1, 12, 12), 0, 180)
        shackle.lineTo(10, 10)
    else:
        shackle.moveTo(10, 15)
        shackle.lineTo(10, 11)
        shackle.arcTo(QRectF(10, 5, 12, 12), 180, -180)
        shackle.lineTo(22, 15)
    painter.drawPath(shackle)
    painter.setBrush(painter.pen().color())
    painter.drawRoundedRect(QRectF(7, 15, 18, 13), 2.5, 2.5)


def _fit(painter: QPainter) -> None:
    for x, y, dx, dy in ((5, 5, 1, 1), (27, 5, -1, 1), (27, 27, -1, -1), (5, 27, 1, -1)):
        painter.drawPolyline([QPointF(x, y + 7 * dy), QPointF(x, y), QPointF(x + 7 * dx, y)])
    painter.drawRect(QRectF(11.5, 11.5, 9, 9))


def _moon(painter: QPainter) -> None:
    crescent = QPainterPath()
    crescent.addEllipse(QRectF(6, 6, 20, 20))
    cut = QPainterPath()
    cut.addEllipse(QRectF(12, 2, 20, 20))
    painter.setBrush(painter.pen().color())
    painter.drawPath(crescent.subtracted(cut))


def _sun(painter: QPainter) -> None:
    painter.setBrush(painter.pen().color())
    painter.drawEllipse(QPointF(16, 16), 5.5, 5.5)
    for i in range(8):
        painter.save()
        painter.translate(16, 16)
        painter.rotate(45 * i)
        painter.drawLine(QPointF(0, -9.5), QPointF(0, -13))
        painter.restore()


def lock_icon(colour: QColor) -> QIcon:
    """Closed when the action is checked (locked), open otherwise."""
    icon = QIcon()
    icon.addPixmap(_icon(lambda p: _padlock(p, False), colour), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_icon(lambda p: _padlock(p, True), colour), QIcon.Mode.Normal, QIcon.State.Off)
    return icon


def fit_icon(colour: QColor) -> QIcon:
    return QIcon(_icon(_fit, colour))


def theme_icon(colour: QColor) -> QIcon:
    """A sun when dark mode is on (checked), a moon when it's off."""
    icon = QIcon()
    icon.addPixmap(_icon(_sun, colour), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_icon(_moon, colour), QIcon.Mode.Normal, QIcon.State.Off)
    return icon
