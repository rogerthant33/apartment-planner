from collections.abc import Iterable

from PySide6.QtCore import QObject, QRectF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from apartment_planner.canvas.items import (
    HandleItem,
    PlacedItem,
    PreviewItem,
    RoomItem,
    RotateHandleItem,
)
from apartment_planner.geometry.handles import Handle, handle_positions
from apartment_planner.geometry.hits import shape_corners
from apartment_planner.model import FurnitureItem, ProjectDoc
from apartment_planner.state.furniture import selected_furniture

# 400 m square around the origin: room to pan, without huge scroll ranges.
SCENE_RECT = QRectF(-20_000, -20_000, 40_000, 40_000)


class PlanScene(QGraphicsScene):
    """Scene units are world cm. Rebuilt from the document after every change."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setSceneRect(SCENE_RECT)
        self.grid_size = 10.0
        self.rooms: list[RoomItem] = []
        self.furniture: list[PlacedItem] = []
        self._extras: list[QGraphicsItem] = []  # handles drawn over the selection
        self.preview = PreviewItem()
        self.addItem(self.preview)
        self.preview.clear()

    def clear_plan(self) -> None:
        for item in [*self.rooms, *self.furniture, *self._extras]:
            self.removeItem(item)
        self.rooms, self.furniture, self._extras = [], [], []
        self.preview.clear()

    def sync(
        self,
        doc: ProjectDoc,
        selection: frozenset[str],
        *,
        editable: bool,
        hidden: Iterable[str] = (),
        rotate_offset: float = 0.0,
    ) -> None:
        """Redraw everything. `rotate_offset` is the rotate handle's distance in cm."""
        self.clear_plan()
        unit = doc.settings.display_unit
        handles = editable and not doc.settings.apartment_locked
        for room in doc.apartment.rooms:
            selected = room.id in selection
            selected_vertex = next((v.id for v in room.vertices if v.id in selection), None)
            item = RoomItem(
                room,
                unit,
                selected=selected,
                handles=selected and handles,
                selected_vertex=selected_vertex,
            )
            self.addItem(item)
            self.rooms.append(item)
        hidden_ids = set(hidden)
        for furniture in doc.active_layout.furniture:
            if furniture.id not in hidden_ids:
                placed = PlacedItem(furniture, unit, selected=furniture.id in selection)
                self.addItem(placed)
                self.furniture.append(placed)
        chosen = selected_furniture(doc, selection)
        if editable and len(chosen) == 1 and not chosen[0].locked:
            self._add_handles(chosen[0], rotate_offset)
        if doc.settings.grid_size != self.grid_size:
            self.grid_size = doc.settings.grid_size
            self.update()

    def _add_handles(self, item: FurnitureItem, rotate_offset: float) -> None:
        for handle, point in handle_positions(item, rotate_offset).items():
            marker: QGraphicsItem = (
                RotateHandleItem(point) if handle is Handle.ROTATE else HandleItem(point, False)
            )
            self.addItem(marker)
            self._extras.append(marker)
        for point in shape_corners(item).values():
            corner = HandleItem(point, False)
            self.addItem(corner)
            self._extras.append(corner)
