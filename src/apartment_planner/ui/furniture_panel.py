"""Properties of selected furniture or obstacles: one item's fields, or actions for several."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from apartment_planner.canvas import style
from apartment_planner.model import FurnitureItem, Placed, PolygonShape, ProjectDoc, Room
from apartment_planner.state.editor import EditorState
from apartment_planner.state.furniture import (
    set_locked,
    set_shape_edge_length,
    shape_edge_lengths,
)
from apartment_planner.state.furniture_fields import FIELDS, field_values, parse_field
from apartment_planner.state.placed import placed_item, update_placed
from apartment_planner.state.units import format_length, parse_length
from apartment_planner.ui.colour_button import ColourButton
from apartment_planner.ui.inline_errors import commit_or_refuse, error_label, show_error


def tool_buttons(actions: list[QAction]) -> QHBoxLayout:
    """A row of text buttons for the window's actions."""
    row = QHBoxLayout()
    for action in actions:
        button = QToolButton()
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        row.addWidget(button)
    row.addStretch()
    return row


def action_buttons(*labels: str) -> tuple[QHBoxLayout, dict[str, QPushButton]]:
    row = QHBoxLayout()
    buttons = {}
    for label in labels:
        button = QPushButton(label)
        row.addWidget(button)
        buttons[label] = button
    row.addStretch()
    return row, buttons


ROTATE_STEP = 15.0  # degrees per click of a turn button, as the rotate handle snaps


class FurniturePage(QWidget):
    """The fields of one furniture item or obstacle. Each commits on Enter or focus-out.

    Obstacles have no room, lock or corner editing, only the fields they share.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state: EditorState | None = None
        self.item_id: str | None = None
        self.editable = False
        self.fields: dict[str, QLineEdit] = {}
        form = QFormLayout()
        self._form = form
        self.colour = ColourButton(lambda: style.colours.furniture_fill)
        self.colour.chosen.connect(self._set_colour)
        for key, label in FIELDS.items():
            field = QLineEdit()
            field.editingFinished.connect(lambda key=key: self._commit_field(key))
            form.addRow(label, field)
            self.fields[key] = field
            if key == "rotation":
                form.addRow("", self._turn_buttons())
            if key == "depth":
                form.addRow("Colour", self.colour)
        clearance = self.fields["clearance"]
        clearance.setPlaceholderText("None")
        tip = (
            "Space to keep free around this item, such as 60 cm in front of a wardrobe "
            "or around a dining table. Anything closer is listed in Fit Checks. "
            "Leave it empty for none."
        )
        clearance.setToolTip(tip)
        form.labelForField(clearance).setToolTip(tip)
        self.title = QLabel()
        self.room = QLabel()
        form.addRow("Room", self.room)
        self.locked = QCheckBox("Locked (can't be moved or resized)")
        self.locked.toggled.connect(self._set_locked)
        self.edges: list[QLineEdit] = []
        self._edge_form = QFormLayout()
        self.edges_title = QLabel("Edge lengths")
        self.error = error_label()
        row, self.buttons = action_buttons("Duplicate", "Delete")

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addLayout(form)
        layout.addWidget(self.locked)
        layout.addWidget(self.edges_title)
        layout.addLayout(self._edge_form)
        layout.addWidget(self.error)
        layout.addLayout(row)
        layout.addStretch()

    def show_item(self, state: EditorState, item: Placed, editable: bool) -> None:
        if item.id != self.item_id:
            show_error(self.error, None)
        self.state, self.item_id, self.editable = None, item.id, editable
        doc = state.doc
        values = field_values(item, doc.settings.display_unit)
        for key, field in self.fields.items():
            self._form.setRowVisible(field, key in values)
            field.setText(values.get(key, ""))
            field.setEnabled(editable)
        self.colour.setEnabled(editable)
        self.colour.show_colour(item.color)
        for turn in self.turn_buttons.values():
            turn.setEnabled(editable)
        furniture = isinstance(item, FurnitureItem)
        self.title.setText("Furniture" if furniture else "Obstacle (part of the apartment)")
        self._form.setRowVisible(self.room, furniture)
        self.locked.setVisible(furniture)
        locked = False
        if isinstance(item, FurnitureItem):
            room = next((r.name for r in doc.apartment.rooms if r.id == item.room_id), "None")
            self.room.setText(room)
            self.locked.setChecked(item.locked)
            locked = item.locked
        self.locked.setEnabled(editable)
        polygon = isinstance(item, FurnitureItem) and isinstance(item.shape, PolygonShape)
        lengths = shape_edge_lengths(item) if isinstance(item, FurnitureItem) and polygon else []
        if len(self.edges) != len(lengths):
            self._rebuild_edges(len(lengths))
        for field, length in zip(self.edges, lengths, strict=True):
            field.setText(format_length(length, doc.settings.display_unit))
            field.setEnabled(editable and not locked)
        self.edges_title.setVisible(polygon)
        for button in self.buttons.values():
            button.setEnabled(editable)
        self.state = state

    def _item(self) -> Placed | None:
        if self.state is None or self.item_id is None:
            return None
        try:
            return placed_item(self.state.doc, self.item_id)
        except KeyError:
            return None

    def _commit_field(self, key: str) -> None:
        item = self._item()
        if item is None or self.state is None:
            return
        unit = self.state.doc.settings.display_unit
        text = self.fields[key].text()
        if text == field_values(item, unit).get(key, ""):
            return
        self._commit(lambda doc: update_placed(doc, item.id, **parse_field(item, key, text, unit)))

    def _turn_buttons(self) -> QWidget:
        """Turn the item anticlockwise or clockwise by ROTATE_STEP."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self.turn_buttons: dict[str, QToolButton] = {}
        for name, text, step in (
            ("anticlockwise", f"↺ {ROTATE_STEP:g}°", -ROTATE_STEP),
            ("clockwise", f"↻ {ROTATE_STEP:g}°", ROTATE_STEP),
        ):
            button = QToolButton()
            button.setText(text)
            button.setToolTip(f"Turn {ROTATE_STEP:g}° {name}")
            button.setAutoRepeat(True)  # hold it down to keep turning
            button.clicked.connect(lambda _=False, step=step: self._turn(step))
            layout.addWidget(button)
            self.turn_buttons[name] = button
        layout.addStretch()
        return row

    def _turn(self, degrees: float) -> None:
        item = self._item()
        if item is not None:
            rotation = item.rotation + degrees
            self._commit(lambda doc: update_placed(doc, item.id, rotation=rotation))

    def _set_colour(self, colour: str | None) -> None:
        item = self._item()
        if item is not None:
            self._commit(lambda doc: update_placed(doc, item.id, color=colour))

    def _set_locked(self, locked: bool) -> None:
        item = self._item()
        if isinstance(item, FurnitureItem) and item.locked != locked:
            self._commit(lambda doc: set_locked(doc, [item.id], locked))

    def _rebuild_edges(self, count: int) -> None:
        for field in self.edges:
            field.editingFinished.disconnect()  # removing a focused field would commit it
        while self._edge_form.rowCount():
            self._edge_form.removeRow(0)
        self.edges = []
        for i in range(count):
            field = QLineEdit()
            field.editingFinished.connect(lambda i=i: self._set_length(i))
            self._edge_form.addRow(f"Edge {i + 1}", field)
            self.edges.append(field)

    def _set_length(self, i: int) -> None:
        item = self._item()
        if not isinstance(item, FurnitureItem) or self.state is None:
            return
        unit = self.state.doc.settings.display_unit
        text = self.edges[i].text()
        if text == format_length(shape_edge_lengths(item)[i], unit):
            return
        length = parse_length(text, unit)
        if length is None:
            self._reject(f"Edge {i + 1}: enter a length such as 80 or 0.8 m.")
            return
        self._commit(lambda doc: set_shape_edge_length(doc, item.id, i, length))

    def _commit(self, change: Callable[[ProjectDoc], ProjectDoc]) -> None:
        assert self.state is not None
        commit_or_refuse(self.state, self.error, change, self._refresh)

    def _reject(self, message: str) -> None:
        show_error(self.error, message)
        self._refresh()

    def _refresh(self) -> None:
        """Put the fields back to the document's values."""
        item, state = self._item(), self.state
        if item is not None and state is not None:
            self.show_item(state, item, self.editable)


class SelectionPage(QWidget):
    """Several selected items: what can be done to them together."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        first, self.buttons = action_buttons("Group", "Ungroup", "Lock", "Unlock")
        second, more = action_buttons("Duplicate", "Delete")
        self.buttons.update(more)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addLayout(first)
        layout.addLayout(second)
        layout.addStretch()

    def show_items(self, items: list[Placed], editable: bool) -> None:
        self.summary.setText(_summary(len(items), "items", [item.name for item in items]))
        furniture = [i for i in items if isinstance(i, FurnitureItem)]  # obstacles: none
        grouped = {item.group_id for item in furniture}
        self.buttons["Group"].setEnabled(
            editable and bool(furniture) and (len(grouped) > 1 or None in grouped)
        )
        self.buttons["Ungroup"].setEnabled(editable and bool(furniture) and grouped != {None})
        self.buttons["Lock"].setEnabled(editable and not all(i.locked for i in furniture))
        self.buttons["Unlock"].setEnabled(editable and any(i.locked for i in furniture))
        for label in ("Duplicate", "Delete"):
            self.buttons[label].setEnabled(editable)


class RoomsPage(QWidget):
    """Several selected rooms: drag one to move them all; they can be deleted together."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        row, self.buttons = action_buttons("Delete")
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addLayout(row)
        layout.addStretch()

    def show_rooms(self, rooms: list[Room], editable: bool) -> None:
        names = [r.name for r in rooms]
        self.summary.setText(_summary(len(rooms), "rooms", names) + " Drag one to move them all.")
        self.buttons["Delete"].setEnabled(editable)


def _summary(count: int, what: str, names: list[str]) -> str:
    listed = ", ".join(names[:5])
    more = f" and {count - 5} more" if count > 5 else ""
    return f"{count} {what} selected: {listed}{more}."
