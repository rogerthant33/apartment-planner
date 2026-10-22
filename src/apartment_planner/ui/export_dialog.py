"""Choosing how to export the plan: PNG resolution, or PDF paper and scale."""

from dataclasses import dataclass, field
from typing import Literal

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from apartment_planner.ui.export import SCALES, PdfOptions

Format = Literal["png", "pdf"]


@dataclass(frozen=True)
class ExportChoice:
    format: Format = "pdf"
    px_per_m: int = 150
    pdf: PdfOptions = field(default_factory=PdfOptions)
    warnings: bool = False


class ExportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Plan")
        self.format = QComboBox()
        self.format.addItem("PDF document", "pdf")
        self.format.addItem("PNG image", "png")
        self.format.currentIndexChanged.connect(self._show_rows)
        self.resolution = QSpinBox()
        self.resolution.setRange(50, 1000)
        self.resolution.setSingleStep(50)
        self.resolution.setValue(150)
        self.resolution.setSuffix(" px per metre")
        self.paper = QComboBox()
        self.paper.addItems(["A4", "A3"])
        self.orientation = QComboBox()
        self.orientation.addItems(["Landscape", "Portrait"])
        self.scale = QComboBox()
        for scale in SCALES:
            self.scale.addItem(f"1:{scale}", scale)
        self.scale.addItem("Fit to page", None)
        self.warnings = QCheckBox("Show fit-check warnings")
        self._form = QFormLayout()
        self._form.addRow("Format", self.format)
        self._form.addRow("Resolution", self.resolution)
        self._form.addRow("Paper", self.paper)
        self._form.addRow("Orientation", self.orientation)
        self._form.addRow("Scale", self.scale)
        self._form.addRow(self.warnings)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(self._form)
        layout.addWidget(buttons)
        self._show_rows()

    def choice(self) -> ExportChoice:
        return ExportChoice(
            format=self.format.currentData(),
            px_per_m=self.resolution.value(),
            pdf=PdfOptions(
                paper="A4" if self.paper.currentText() == "A4" else "A3",
                landscape=self.orientation.currentText() == "Landscape",
                scale=self.scale.currentData(),
            ),
            warnings=self.warnings.isChecked(),
        )

    def _show_rows(self) -> None:
        pdf = self.format.currentData() == "pdf"
        for widget, shown in (
            (self.resolution, not pdf),
            (self.paper, pdf),
            (self.orientation, pdf),
            (self.scale, pdf),
        ):
            self._form.setRowVisible(widget, shown)
