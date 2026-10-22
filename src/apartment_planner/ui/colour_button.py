"""Picking a fill colour: a swatch button that opens the colour dialog, and a
button to go back to the default fill."""

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from apartment_planner.ui import dialogs

SWATCH = QSize(36, 16)


class ColourButton(QWidget):
    chosen = Signal(object)  # the new colour as #rrggbb, or None for the default

    def __init__(self, default: Callable[[], QColor], parent: QWidget | None = None) -> None:
        """`default` gives the fill used when no colour is chosen, in the current theme;
        the colour dialog starts from it."""
        super().__init__(parent)
        self.colour: str | None = None
        self._default = default
        self.swatch = QToolButton()
        self.swatch.setIconSize(SWATCH)
        self.swatch.setToolTip("Choose a fill colour")
        self.swatch.clicked.connect(self._choose)
        self.reset = QToolButton()
        self.reset.setText("Default")
        self.reset.setToolTip("Use the default fill")
        self.reset.clicked.connect(lambda: self._set(None))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.swatch)
        layout.addWidget(self.reset)
        layout.addStretch()
        self.show_colour(None)

    def show_colour(self, colour: str | None) -> None:
        """Show `colour` without reporting it as chosen."""
        self.colour = colour
        pixmap = QPixmap(SWATCH)
        pixmap.fill(QColor(colour) if colour else QColor(0, 0, 0, 0))
        self.swatch.setIcon(QIcon(pixmap))
        self.swatch.setText("" if colour else "None")
        self.swatch.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if colour
            else Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.reset.setEnabled(self.isEnabled() and colour is not None)

    def _choose(self) -> None:
        start = QColor(self.colour) if self.colour else self._default()
        start.setAlpha(255)
        picked = dialogs.choose_colour(self, start)
        if picked is not None:
            self._set(picked)

    def _set(self, colour: str | None) -> None:
        if colour != self.colour:
            self.show_colour(colour)
            self.chosen.emit(colour)
