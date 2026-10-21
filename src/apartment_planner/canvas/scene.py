from PySide6.QtCore import QObject, QRectF
from PySide6.QtWidgets import QGraphicsScene

from apartment_planner.canvas.items import PreviewItem, RoomItem
from apartment_planner.model import ProjectDoc

# 400 m square around the origin: room to pan, without huge scroll ranges.
SCENE_RECT = QRectF(-20_000, -20_000, 40_000, 40_000)


class PlanScene(QGraphicsScene):
    """Scene units are world cm. Rebuilt from the document after every change."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setSceneRect(SCENE_RECT)
        self.grid_size = 10.0
        self.rooms: list[RoomItem] = []
        self.preview = PreviewItem()
        self.addItem(self.preview)
        self.preview.clear()

    def clear_plan(self) -> None:
        for item in self.rooms:
            self.removeItem(item)
        self.rooms = []
        self.preview.clear()

    def sync(self, doc: ProjectDoc, selection: frozenset[str], *, editable: bool) -> None:
        self.clear_plan()
        handles = editable and not doc.settings.apartment_locked
        for room in doc.apartment.rooms:
            selected = room.id in selection
            selected_vertex = next((v.id for v in room.vertices if v.id in selection), None)
            item = RoomItem(
                room,
                doc.settings.display_unit,
                selected=selected,
                handles=selected and handles,
                selected_vertex=selected_vertex,
            )
            self.addItem(item)
            self.rooms.append(item)
        if doc.settings.grid_size != self.grid_size:
            self.grid_size = doc.settings.grid_size
            self.update()
