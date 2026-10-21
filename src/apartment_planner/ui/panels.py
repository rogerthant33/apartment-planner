"""Side panels: tools and rooms on the left, properties on the right.

Panels read from EditorState and change the document only through it. Fields
commit on Enter or when they lose focus.
"""

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from apartment_planner.geometry.polygon import edge_lengths
from apartment_planner.geometry.shapes import room_polygon
from apartment_planner.model import ProjectDoc, Room
from apartment_planner.state.editor import EditorState
from apartment_planner.state.rooms import (
    EditError,
    rename_room,
    selected_room,
    set_edge_length,
)
from apartment_planner.state.units import Unit, format_area, format_length, parse_length

ROOM_ID = Qt.ItemDataRole.UserRole
UNITS: tuple[Unit, ...] = ("mm", "cm", "m")


def error_label() -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    label.setStyleSheet("color: #d32f2f;")
    label.hide()
    return label


def show_error(label: QLabel, message: str | None) -> None:
    label.setText(message or "")
    label.setVisible(message is not None)


class ToolsPanel(QWidget):
    """Tool buttons and the list of rooms."""

    room_activated = Signal(str)

    def __init__(self, tool_actions: list[QAction], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        tools = QHBoxLayout()
        for action in tool_actions:
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            tools.addWidget(button)
        tools.addStretch()
        self.rooms = QListWidget()
        self.rooms.itemClicked.connect(lambda item: self.room_activated.emit(item.data(ROOM_ID)))
        layout = QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(QLabel("Rooms"))
        layout.addWidget(self.rooms, 1)

    def refresh(self, doc: ProjectDoc, selection: frozenset[str]) -> None:
        self.rooms.blockSignals(True)
        entries = [(room.id, room.name) for room in doc.apartment.rooms]
        # Rebuild only when the rooms change: this can run inside the list's own
        # click handler, which mustn't lose the clicked item.
        if entries != self._entries():
            self.rooms.clear()
            for room_id, name in entries:
                item = QListWidgetItem(name)
                item.setData(ROOM_ID, room_id)
                self.rooms.addItem(item)
        for i, (room_id, _) in enumerate(entries):
            self.rooms.item(i).setSelected(room_id in selection)
        self.rooms.setEnabled(not doc.settings.apartment_locked)
        self.rooms.blockSignals(False)

    def _entries(self) -> list[tuple[str, str]]:
        items = (self.rooms.item(i) for i in range(self.rooms.count()))
        return [(item.data(ROOM_ID), item.text()) for item in items]


class RoomPage(QWidget):
    """Name, area and edge lengths of the selected room."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state: EditorState | None = None
        self.room_id: str | None = None
        self.editable = False
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._rename)
        self.area = QLabel()
        self.edges: list[QLineEdit] = []
        self._edge_form = QFormLayout()
        self.error = error_label()
        self.duplicate = QPushButton("Duplicate")
        self.delete = QPushButton("Delete")
        buttons = QHBoxLayout()
        buttons.addWidget(self.duplicate)
        buttons.addWidget(self.delete)
        buttons.addStretch()

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Area", self.area)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Edge lengths"))
        layout.addLayout(self._edge_form)
        layout.addWidget(self.error)
        layout.addLayout(buttons)
        layout.addStretch()

    def show_room(self, state: EditorState, room: Room, editable: bool) -> None:
        if room.id != self.room_id:
            show_error(self.error, None)
        self.state, self.room_id, self.editable = state, room.id, editable
        unit = state.doc.settings.display_unit
        self.name.setText(room.name)
        self.area.setText(format_area(room_polygon(room).area))
        lengths = edge_lengths(room.vertices)
        if len(self.edges) != len(lengths):
            self._rebuild_edges(len(lengths))
        for field, length in zip(self.edges, lengths, strict=True):
            field.setText(format_length(length, unit))
        for widget in (self.name, *self.edges, self.duplicate, self.delete):
            widget.setEnabled(editable)

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

    def _room(self) -> Room | None:
        if self.state is None:
            return None
        return next((r for r in self.state.doc.apartment.rooms if r.id == self.room_id), None)

    def _rename(self) -> None:
        room = self._room()
        if room is not None and self.state is not None and self.name.text() != room.name:
            self._commit(lambda doc: rename_room(doc, room.id, self.name.text()))

    def _set_length(self, i: int) -> None:
        room = self._room()
        if room is None or self.state is None:
            return
        unit = self.state.doc.settings.display_unit
        current = edge_lengths(room.vertices)[i]
        text = self.edges[i].text()
        if text == format_length(current, unit):
            return
        length = parse_length(text, unit)
        if length is None:
            self._reject(f"Edge {i + 1}: enter a length such as 250 or 2.5 m.")
            return
        vertex_id = room.vertices[i].id
        self._commit(lambda doc: set_edge_length(doc, room.id, vertex_id, length))

    def _commit(self, change: Callable[[ProjectDoc], ProjectDoc]) -> None:
        assert self.state is not None
        try:
            doc = change(self.state.doc)
        except EditError as error:
            self._reject(str(error))
            return
        show_error(self.error, None)
        self.state.commit(doc)

    def _reject(self, message: str) -> None:
        """Inline refusal: the fields go back to the document's values."""
        show_error(self.error, message)
        room = self._room()
        if room is not None and self.state is not None:
            self.show_room(self.state, room, self.editable)


class SettingsPage(QWidget):
    """Project settings, shown when nothing is selected. Not part of undo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state: EditorState | None = None
        self.unit = QComboBox()
        self.unit.addItems(list(UNITS))
        self.unit.currentTextChanged.connect(self._set_unit)
        self.grid = QLineEdit()
        self.grid.editingFinished.connect(self._set_grid)
        self.snap = QCheckBox("Snap to grid and rooms")
        self.snap.toggled.connect(self._set_snap)
        self.error = error_label()
        form = QFormLayout()
        form.addRow("Units", self.unit)
        form.addRow("Grid size", self.grid)
        form.addRow(self.snap)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Project settings"))
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addStretch()

    def show_settings(self, state: EditorState, editable: bool) -> None:
        self.state = None  # don't write back while filling the fields
        settings = state.doc.settings
        self.unit.setCurrentText(settings.display_unit)
        self.grid.setText(format_length(settings.grid_size, settings.display_unit))
        self.snap.setChecked(settings.snap_enabled)
        for widget in (self.unit, self.grid, self.snap):
            widget.setEnabled(editable)
        self.state = state

    def _update(self, **changes: object) -> None:
        if self.state is not None:
            doc = self.state.doc
            self.state.update_untracked(doc.evolve(settings=doc.settings.evolve(**changes)))

    def _set_unit(self, unit: str) -> None:
        self._update(display_unit=unit)

    def _set_snap(self, enabled: bool) -> None:
        self._update(snap_enabled=enabled)

    def _set_grid(self) -> None:
        if self.state is None:
            return
        settings = self.state.doc.settings
        size = parse_length(self.grid.text(), settings.display_unit)
        if size is None or size <= 0:
            show_error(self.error, "Grid size: enter a length greater than 0, such as 10 cm.")
            self.grid.setText(format_length(settings.grid_size, settings.display_unit))
            return
        show_error(self.error, None)
        self._update(grid_size=size)


class PropertiesPanel(QStackedWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings_page = SettingsPage()
        self.room_page = RoomPage()
        self.addWidget(self.settings_page)
        self.addWidget(self.room_page)

    def refresh(self, state: EditorState, editable: bool) -> None:
        room = selected_room(state.doc, state.selection)
        if room is None:
            self.settings_page.show_settings(state, editable)
            self.setCurrentWidget(self.settings_page)
        else:
            self.room_page.show_room(state, room, editable)
            self.setCurrentWidget(self.room_page)
