"""Plan export to PNG and PDF. See docs/SPEC.md §9.

The active layout is drawn by a scene of its own (no selection, grid or
background image), with every room's edge lengths, a title and a scale bar.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from apartment_planner.canvas import style
from apartment_planner.canvas.scene import PlanScene
from apartment_planner.fit.findings import check_fit
from apartment_planner.geometry.paper import fitting_scale, scale_bar_length
from apartment_planner.geometry.shapes import plan_bounds
from apartment_planner.model import ProjectDoc
from apartment_planner.state.units import format_length

MARGIN_CM = 50.0  # world space kept around the plan
TITLE_PT = 14.0
BAND = 3.0  # title and scale-bar bands, in title heights
POINT_MM = 25.4 / 72  # PDFs are drawn in points
PAPER_MARGIN_MM = 10.0
SCALES = (50, 100)


class ExportError(Exception):
    """An export that couldn't be made; the message says why and what to do."""


def _write_failed(path: Path) -> ExportError:
    return ExportError(
        f"Couldn't write {path.name}. Check that you can change files in that folder."
    )


@dataclass(frozen=True)
class PdfOptions:
    paper: Literal["A4", "A3"] = "A4"
    landscape: bool = True
    scale: int | None = 50  # 1:scale, or None to fit the page


def plan_rect(doc: ProjectDoc) -> QRectF:
    """The world area to draw: the rooms, obstacles and furniture, with a margin."""
    found = plan_bounds(
        doc.apartment.rooms, [*doc.apartment.obstacles, *doc.active_layout.furniture]
    )
    if found is None:
        raise ExportError("There's nothing to export yet. Draw a room first.")
    left, top, right, bottom = found
    rect = QRectF(left, top, right - left, bottom - top)
    return rect.adjusted(-MARGIN_CM, -MARGIN_CM, MARGIN_CM, MARGIN_CM)


def export_png(doc: ProjectDoc, path: Path, px_per_m: float = 150, warnings: bool = False) -> None:
    """Raises ExportError if there's nothing to draw or the file can't be written."""
    source = plan_rect(doc)
    per_cm = px_per_m / 100
    band = _band_height()
    image = QImage(
        round(source.width() * per_cm),
        round(source.height() * per_cm + 2 * band),
        QImage.Format.Format_RGB32,
    )
    image.fill(QColor("white"))
    painter = QPainter(image)
    target = QRectF(0, band, image.width(), image.height() - 2 * band)
    _draw(painter, doc, source, target, per_cm, _title(doc, None), warnings)
    painter.end()
    # PySide's stubs say the format is bytes, but at run time it must be a str.
    if not image.save(str(path), "PNG"):  # type: ignore[call-overload]
        raise _write_failed(path)


def export_pdf(
    doc: ProjectDoc, path: Path, options: PdfOptions, warnings: bool = False
) -> int | None:
    """Draw the plan to scale if it fits on the page, otherwise fitted to it.
    Returns the scale used, or None if it was fitted."""
    source = plan_rect(doc)
    writer = QPdfWriter(str(path))
    writer.setResolution(72)  # device units are points
    size = QPageSize.PageSizeId.A4 if options.paper == "A4" else QPageSize.PageSizeId.A3
    orientation = (
        QPageLayout.Orientation.Landscape if options.landscape else QPageLayout.Orientation.Portrait
    )
    margins = QMarginsF(*[PAPER_MARGIN_MM] * 4)
    writer.setPageLayout(
        QPageLayout(QPageSize(size), orientation, margins, QPageLayout.Unit.Millimeter)
    )
    band = _band_height()
    area = QRectF(0, band, writer.width(), writer.height() - 2 * band)
    area_mm = (area.width() * POINT_MM, area.height() * POINT_MM)
    content = (source.width(), source.height())
    scale = None
    if options.scale is not None:
        scale = fitting_scale(content, area_mm, [options.scale])
    if scale is not None:
        per_cm = 10 / scale / POINT_MM  # points per world cm
    else:
        per_cm = min(area.width() / source.width(), area.height() / source.height())
    width, height = source.width() * per_cm, source.height() * per_cm
    target = QRectF(area.x() + (area.width() - width) / 2, area.y(), width, height)
    painter = QPainter()
    if not painter.begin(writer):
        raise _write_failed(path)
    _draw(painter, doc, source, target, per_cm, _title(doc, scale), warnings)
    painter.end()
    return scale


def _title(doc: ProjectDoc, scale: int | None) -> str:
    title = f"{doc.name} — {doc.active_layout.name}"
    return title if scale is None else f"{title} · 1:{scale}"


def _title_font() -> QFont:
    font = QFont()
    font.setPointSizeF(TITLE_PT)
    return font


def _band_height() -> float:
    return TITLE_PT * BAND


def _draw(
    painter: QPainter,
    doc: ProjectDoc,
    source: QRectF,
    target: QRectF,
    per_cm: float,
    title: str,
    warnings: bool,
) -> None:
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    scene = PlanScene()
    findings = check_fit(doc.apartment, doc.active_layout, doc.settings.default_clearance)
    scene.sync(
        doc,
        frozenset(),
        editable=False,
        findings=findings if warnings else (),
        dimensions=True,
    )
    scene.preview.hide()
    scene.render(painter, target, source, Qt.AspectRatioMode.KeepAspectRatio)
    band = _band_height()
    painter.setPen(style.LABEL)
    painter.setFont(_title_font())
    painter.drawText(
        QRectF(target.left() + band / 3, target.top() - band, target.width(), band),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        title,
    )
    length = scale_bar_length(source.width() / 4)
    left = target.left() + band / 3
    y = target.bottom() + band / 2
    right = left + length * per_cm
    painter.setPen(QPen(style.ROOM_OUTLINE, 1.5))
    painter.drawLine(QPointF(left, y), QPointF(right, y))
    for x in (left, right):
        painter.drawLine(QPointF(x, y - 4), QPointF(x, y + 4))
    font = _title_font()
    font.setPointSizeF(TITLE_PT * 0.7)
    painter.setFont(font)
    painter.drawText(
        QRectF(right + 8, y - band / 2, band * 4, band),
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        format_length(length, doc.settings.display_unit),
    )
