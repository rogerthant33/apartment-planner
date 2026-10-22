"""Background image controls, shown with the project settings. See docs/SPEC.md §10."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from apartment_planner.model import ProjectDoc
from apartment_planner.state.background import remove_background, update_background
from apartment_planner.state.editor import EditorState
from apartment_planner.state.units import parse_angle
from apartment_planner.ui.inline_errors import commit_or_refuse, error_label


class BackgroundBox(QGroupBox):
    """Import, move, calibrate, turn, fade, hide, lock or remove the image."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Background image", parent)
        self.state: EditorState | None = None
        self.hint = QLabel("Import a floor plan to trace rooms over it.")
        self.hint.setWordWrap(True)
        self._buttons = QHBoxLayout()
        self._buttons.addStretch()
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        # Dragging commits once, on release; keys, the wheel and clicks on the track
        # commit each step.
        self.opacity.sliderReleased.connect(self._set_opacity)
        self.opacity.valueChanged.connect(
            lambda _: None if self.opacity.isSliderDown() else self._set_opacity()
        )
        self.rotation = QLineEdit()
        self.rotation.editingFinished.connect(self._set_rotation)
        self.visible = QCheckBox("Shown")
        self.visible.toggled.connect(lambda shown: self._change(visible=shown))
        self.locked = QCheckBox("Locked (can't be moved)")
        self.locked.toggled.connect(lambda locked: self._change(locked=locked))
        self.remove = QPushButton("Remove")
        self.remove.clicked.connect(lambda: self._commit(remove_background))
        self.error = error_label()
        self._form = QFormLayout()
        self._form.addRow("Opacity", self.opacity)
        self._form.addRow("Rotation", self.rotation)
        self._form.addRow(self.visible)
        self._form.addRow(self.locked)
        layout = QVBoxLayout(self)
        layout.addWidget(self.hint)
        layout.addLayout(self._buttons)
        layout.addLayout(self._form)
        layout.addWidget(self.error)
        layout.addWidget(self.remove)

    def add_actions(self, actions: list[QAction]) -> None:
        """Buttons for the window's actions: import, move and calibrate."""
        for action in actions:
            button = QToolButton()
            button.setDefaultAction(action)
            self._buttons.insertWidget(self._buttons.count() - 1, button)

    def show_background(self, state: EditorState, editable: bool) -> None:
        self.state = None  # don't write back while filling the fields
        bg = state.doc.background
        for widget in (self.opacity, self.rotation, self.visible, self.locked, self.remove):
            widget.setVisible(bg is not None)
            widget.setEnabled(editable)
            label = self._form.labelForField(widget)
            if label is not None:
                label.setVisible(bg is not None)
        self.hint.setText(
            "Import a floor plan to trace rooms over it."
            if bg is None
            else f"{bg.cm_per_pixel:.3g} cm per pixel. Calibrate to set the scale."
        )
        if bg is not None:
            self.opacity.setValue(round(bg.opacity * 100))
            self.rotation.setText(f"{bg.rotation:g}°")
            self.visible.setChecked(bg.visible)
            self.locked.setChecked(bg.locked)
        self.state = state

    def _set_opacity(self) -> None:
        self._change(opacity=self.opacity.value() / 100)

    def _set_rotation(self) -> None:
        text = self.rotation.text()
        self._commit(lambda doc: update_background(doc, rotation=parse_angle(text, "Rotation")))

    def _change(self, **changes: object) -> None:
        bg = self.state.doc.background if self.state is not None else None
        if bg is not None and any(getattr(bg, k) != v for k, v in changes.items()):
            self._commit(lambda doc: update_background(doc, **changes))

    def _commit(self, change: Callable[[ProjectDoc], ProjectDoc]) -> None:
        state = self.state
        if state is not None:
            commit_or_refuse(
                state, self.error, change, lambda: self.show_background(state, self.isEnabled())
            )
