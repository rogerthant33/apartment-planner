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
from apartment_planner.model import FurnitureItem, ProjectDoc, Room
from apartment_planner.state.editor import EditorState
from apartment_planner.state.errors import EditError
from apartment_planner.state.openings import selected_openings
from apartment_planner.state.placed import selected_placed
from apartment_planner.state.rooms import (
    recolour_room,
    rename_room,
    selected_room,
    selected_rooms,
    set_edge_length,
)
from apartment_planner.state.units import Unit, format_area, format_length, parse_length
from apartment_planner.ui.background_panel import BackgroundBox
from apartment_planner.ui.colour_button import ColourButton
from apartment_planner.ui.furniture_panel import FurniturePage, SelectionPage
from apartment_planner.ui.inline_errors import error_label, show_error
from apartment_planner.ui.opening_panel import OpeningPage

ROOM_ID = Qt.ItemDataRole.UserRole  # the ID of a list entry's room or item
UNITS: tuple[Unit, ...] = ("mm", "cm", "m")


class ToolsPanel(QWidget):
    """Layout switcher, tools, and the lists of rooms and furniture."""

    room_activated = Signal(str)
    furniture_activated = Signal(str)
    visibility_changed = Signal(frozenset)  # the IDs of hidden furniture
    layout_chosen = Signal(str)

    def __init__(
        self,
        tool_actions: list[QAction],
        apartment_actions: list[QAction],
        add_actions: list[QAction],
        layout_actions: list[QAction],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.layouts = QComboBox()
        self.layouts.activated.connect(lambda i: self.layout_chosen.emit(self.layouts.itemData(i)))
        layout_row = QHBoxLayout()
        layout_row.addWidget(self.layouts, 1)
        layout_row.addLayout(_buttons(layout_actions))
        self.rooms = QListWidget()
        self.rooms.itemClicked.connect(lambda item: self.room_activated.emit(item.data(ROOM_ID)))
        self.furniture = QListWidget()
        self.furniture.itemClicked.connect(self._furniture_clicked)
        self.furniture.itemChanged.connect(lambda _: self.visibility_changed.emit(self.hidden()))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Layout"))
        layout.addLayout(layout_row)
        layout.addWidget(QLabel("Tools"))
        layout.addLayout(_buttons(tool_actions))
        layout.addWidget(QLabel("Add to the apartment (unlock it first)"))
        layout.addLayout(_buttons(apartment_actions))
        layout.addWidget(QLabel("Add furniture"))
        layout.addLayout(_buttons(add_actions))
        layout.addWidget(QLabel("Rooms"))
        layout.addWidget(self.rooms, 1)
        layout.addWidget(QLabel("Furniture (untick to hide)"))
        layout.addWidget(self.furniture, 2)

    def refresh(self, doc: ProjectDoc, selection: frozenset[str], hidden: frozenset[str]) -> None:
        self.layouts.blockSignals(True)
        self.layouts.clear()
        for layout in doc.layouts:
            self.layouts.addItem(layout.name, layout.id)
        self.layouts.setCurrentIndex(
            [layout.id for layout in doc.layouts].index(doc.active_layout_id)
        )
        self.layouts.blockSignals(False)
        # Lists are rebuilt only when their entries change: this can run inside a
        # list's own click handler, which mustn't lose the clicked item.
        rooms = [(room.id, room.name) for room in doc.apartment.rooms]
        _sync_list(self.rooms, rooms, selection)
        self.rooms.setEnabled(not doc.settings.apartment_locked)
        furniture = [(item.id, item.name) for item in doc.active_layout.furniture]
        _sync_list(self.furniture, furniture, selection, checked=lambda i: i not in hidden)

    def hidden(self) -> frozenset[str]:
        items = (self.furniture.item(i) for i in range(self.furniture.count()))
        return frozenset(
            item.data(ROOM_ID) for item in items if item.checkState() == Qt.CheckState.Unchecked
        )

    def _furniture_clicked(self, item: QListWidgetItem) -> None:
        if item.checkState() == Qt.CheckState.Checked:
            self.furniture_activated.emit(item.data(ROOM_ID))


def _buttons(actions: list[QAction]) -> QHBoxLayout:
    row = QHBoxLayout()
    for action in actions:
        button = QToolButton()
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        row.addWidget(button)
    row.addStretch()
    return row


def _sync_list(
    widget: QListWidget,
    entries: list[tuple[str, str]],
    selection: frozenset[str],
    checked: Callable[[str], bool] | None = None,
) -> None:
    widget.blockSignals(True)
    current = [(widget.item(i).data(ROOM_ID), widget.item(i).text()) for i in range(widget.count())]
    if entries != current:
        widget.clear()
        for entry_id, name in entries:
            item = QListWidgetItem(name)
            item.setData(ROOM_ID, entry_id)
            widget.addItem(item)
    for i, (entry_id, _) in enumerate(entries):
        item = widget.item(i)
        item.setSelected(entry_id in selection)
        if checked is not None:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if checked(entry_id) else Qt.CheckState.Unchecked
            )
    widget.blockSignals(False)


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
        self.colour = ColourButton()
        self.colour.chosen.connect(self._set_colour)
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
        form.addRow("Colour", self.colour)
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
        for widget in (self.name, *self.edges, self.duplicate, self.delete, self.colour):
            widget.setEnabled(editable)
        self.colour.show_colour(room.color)

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

    def _set_colour(self, colour: str | None) -> None:
        room = self._room()
        if room is not None and self.state is not None:
            self._commit(lambda doc: recolour_room(doc, room.id, colour))

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
    """Project settings, shown when nothing is selected. Not part of undo.

    The background image controls below them are: the image is part of the plan.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.background = BackgroundBox()
        self.state: EditorState | None = None
        self.unit = QComboBox()
        self.unit.addItems(list(UNITS))
        self.unit.currentTextChanged.connect(self._set_unit)
        self.grid = QLineEdit()
        self.grid.editingFinished.connect(self._set_grid)
        self.snap = QCheckBox("Snap to grid and rooms")
        self.snap.toggled.connect(self._set_snap)
        self.doorway = QLineEdit()
        self.doorway.setToolTip("How far in front of doorways furniture counts as in the way")
        self.doorway.editingFinished.connect(self._set_doorway)
        self.error = error_label()
        form = QFormLayout()
        form.addRow("Units", self.unit)
        form.addRow("Grid size", self.grid)
        form.addRow(self.snap)
        form.addRow("Doorway clearance", self.doorway)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Project settings"))
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(self.background)
        layout.addStretch()

    def show_settings(self, state: EditorState, editable: bool) -> None:
        self.background.show_background(state, editable)
        self.state = None  # don't write back while filling the fields
        settings = state.doc.settings
        self.unit.setCurrentText(settings.display_unit)
        self.grid.setText(format_length(settings.grid_size, settings.display_unit))
        self.snap.setChecked(settings.snap_enabled)
        self.doorway.setText(format_length(settings.default_clearance, settings.display_unit))
        for widget in (self.unit, self.grid, self.snap, self.doorway):
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

    def _set_doorway(self) -> None:
        if self.state is None:
            return
        settings = self.state.doc.settings
        depth = parse_length(self.doorway.text(), settings.display_unit)
        if depth is None:
            show_error(self.error, "Doorway clearance: enter a length such as 60, or 0 for none.")
            self.doorway.setText(format_length(settings.default_clearance, settings.display_unit))
            return
        show_error(self.error, None)
        self._update(default_clearance=depth)


class PropertiesPanel(QStackedWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings_page = SettingsPage()
        self.room_page = RoomPage()
        self.furniture_page = FurniturePage()
        self.selection_page = SelectionPage()
        self.opening_page = OpeningPage()
        for page in (
            self.settings_page,
            self.room_page,
            self.furniture_page,
            self.selection_page,
            self.opening_page,
        ):
            self.addWidget(page)

    def refresh(self, state: EditorState, editable: bool) -> None:
        doc = state.doc
        placed = selected_placed(doc, state.selection)
        openings = selected_openings(doc, state.selection)
        room = selected_room(doc, state.selection)
        rooms = selected_rooms(doc, state.selection)
        # Obstacles and openings belong to the apartment, which may be locked.
        apartment = editable and not doc.settings.apartment_locked
        if placed and not isinstance(placed[0], FurnitureItem):
            editable = apartment
        if len(placed) > 1:
            self.selection_page.show_items(placed, editable)
            self.setCurrentWidget(self.selection_page)
        elif placed:
            self.furniture_page.show_item(state, placed[0], editable)
            self.setCurrentWidget(self.furniture_page)
        elif len(rooms) > 1:
            self.selection_page.show_rooms(rooms, editable and not doc.settings.apartment_locked)
            self.setCurrentWidget(self.selection_page)
        elif openings:
            self.opening_page.show_opening(state, openings[0], apartment)
            self.setCurrentWidget(self.opening_page)
        elif room is not None:
            self.room_page.show_room(state, room, editable)
            self.setCurrentWidget(self.room_page)
        else:
            self.settings_page.show_settings(state, editable)
            self.setCurrentWidget(self.settings_page)
