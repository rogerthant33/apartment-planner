"""A text box over a name label on the plan, for renaming in place."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget


class NameEditor(QLineEdit):
    """Starts with `name` selected. Enter, or clicking elsewhere, reports the text
    once through `chosen`; Escape closes it without a change."""

    chosen = Signal(str)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(name, parent)
        self.setToolTip("Enter to rename, Escape to cancel")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._open = True
        self.editingFinished.connect(self._choose)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_without_change()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)  # emits editingFinished: clicking away saves
        self.close_without_change()

    def close_without_change(self) -> None:
        self._open = False
        self.hide()
        self.deleteLater()

    def _choose(self) -> None:
        if self._open:
            self._open = False
            self.chosen.emit(self.text())
            self.close_without_change()
