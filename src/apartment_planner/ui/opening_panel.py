"""Properties of the selected door, window or plain opening."""

from collections.abc import Callable
from typing import Any, Literal

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from apartment_planner.model import DoorSpec, Opening, ProjectDoc
from apartment_planner.state.editor import EditorState
from apartment_planner.state.errors import EditError
from apartment_planner.state.openings import opening, parse_opening_length, update_opening
from apartment_planner.state.rooms import room
from apartment_planner.state.units import format_length
from apartment_planner.ui.furniture_panel import action_buttons
from apartment_planner.ui.inline_errors import error_label, show_error

KINDS = {"door": "Door", "window": "Window", "opening": "Opening (no door)"}
HINGES = {"start": "At the wall's start", "end": "At the wall's end"}
SWINGS = {"in": "Into the room", "out": "Out of the room"}


def _combo(choices: dict[str, str]) -> QComboBox:
    combo = QComboBox()
    for value, text in choices.items():
        combo.addItem(text, value)
    return combo


class OpeningPage(QWidget):
    """Kind, size and position of one opening, and a door's hinge and swing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state: EditorState | None = None
        self.opening_id: str | None = None
        self.editable = False
        self.wall = QLabel()
        self.kind = _combo(KINDS)
        self.kind.activated.connect(lambda _: self._commit(kind=self.kind.currentData()))
        self.width_field = QLineEdit()
        self.width_field.editingFinished.connect(lambda: self._commit_length("width"))
        self.offset_field = QLineEdit()
        self.offset_field.editingFinished.connect(lambda: self._commit_length("offset"))
        self.offset_field.setToolTip("Distance from the wall's start to the opening's centre")
        self.hinge = _combo(HINGES)
        self.hinge.activated.connect(lambda _: self._commit_door(hinge=self.hinge.currentData()))
        self.swing = _combo(SWINGS)
        self.swing.activated.connect(lambda _: self._commit_door(swing=self.swing.currentData()))
        self.error = error_label()
        row, self.buttons = action_buttons("Delete")

        self._form = QFormLayout()
        self._form.addRow("Wall", self.wall)
        self._form.addRow("Kind", self.kind)
        self._form.addRow("Width", self.width_field)
        self._form.addRow("Offset", self.offset_field)
        self._form.addRow("Hinge", self.hinge)
        self._form.addRow("Swing", self.swing)
        layout = QVBoxLayout(self)
        layout.addLayout(self._form)
        layout.addWidget(self.error)
        layout.addLayout(row)
        layout.addStretch()

    def show_opening(self, state: EditorState, shown: Opening, editable: bool) -> None:
        if shown.id != self.opening_id:
            show_error(self.error, None)
        self.state, self.opening_id, self.editable = state, shown.id, editable
        doc = state.doc
        unit = doc.settings.display_unit
        owner = room(doc, shown.room_id)
        number = [v.id for v in owner.vertices].index(shown.edge_start_vertex_id) + 1
        self.wall.setText(f"{owner.name}, edge {number}")
        self.kind.setCurrentIndex(list(KINDS).index(shown.kind))
        self.width_field.setText(format_length(shown.width, unit))
        self.offset_field.setText(format_length(shown.offset, unit))
        door = shown.door is not None
        if shown.door is not None:
            self.hinge.setCurrentIndex(list(HINGES).index(shown.door.hinge))
            self.swing.setCurrentIndex(list(SWINGS).index(shown.door.swing))
        for combo in (self.hinge, self.swing):
            combo.setVisible(door)
            self._form.labelForField(combo).setVisible(door)
        for widget in (self.kind, self.width_field, self.offset_field, self.hinge, self.swing):
            widget.setEnabled(editable)
        self.buttons["Delete"].setEnabled(editable)

    def _opening(self) -> Opening | None:
        if self.state is None or self.opening_id is None:
            return None
        try:
            return opening(self.state.doc, self.opening_id)
        except KeyError:
            return None

    def _commit_length(self, key: Literal["width", "offset"]) -> None:
        current, state = self._opening(), self.state
        if current is None or state is None:
            return
        field = self.width_field if key == "width" else self.offset_field
        unit = state.doc.settings.display_unit
        if field.text() == format_length(getattr(current, key), unit):
            return
        self._apply(
            lambda doc: update_opening(
                doc, current.id, **parse_opening_length(doc, current, key, field.text(), unit)
            )
        )

    def _commit_door(self, **changes: str) -> None:
        current = self._opening()
        if current is not None and current.door is not None:
            self._commit(door=DoorSpec(**{**current.door.model_dump(), **changes}))

    def _commit(self, **changes: Any) -> None:
        current = self._opening()
        if current is not None and any(getattr(current, k) != v for k, v in changes.items()):
            self._apply(lambda doc: update_opening(doc, current.id, **changes))

    def _apply(self, change: Callable[[ProjectDoc], ProjectDoc]) -> None:
        assert self.state is not None
        try:
            doc = change(self.state.doc)
        except EditError as error:
            show_error(self.error, str(error))
            current = self._opening()
            if current is not None:
                self.show_opening(self.state, current, self.editable)
            return
        show_error(self.error, None)
        self.state.commit(doc)
