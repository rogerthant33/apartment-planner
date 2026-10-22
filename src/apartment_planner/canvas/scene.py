import math
from collections.abc import Iterable, Sequence

from PySide6.QtCore import QObject, QRectF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from apartment_planner.canvas.items import (
    ClearanceItem,
    HandleItem,
    OpeningItem,
    PlacedItem,
    PreviewItem,
    ReadoutItem,
    RoomItem,
    RotateHandleItem,
)
from apartment_planner.fit.findings import Finding, Severity
from apartment_planner.geometry.constants import EPS
from apartment_planner.geometry.handles import Handle, handle_positions
from apartment_planner.geometry.hits import shape_corners
from apartment_planner.geometry.readouts import Segment, gap_between, wall_gaps
from apartment_planner.model import FurnitureItem, Placed, ProjectDoc
from apartment_planner.state.placed import selected_placed
from apartment_planner.state.units import Unit, format_length

# 400 m square around the origin: room to pan, without huge scroll ranges.
SCENE_RECT = QRectF(-20_000, -20_000, 40_000, 40_000)


class PlanScene(QGraphicsScene):
    """Scene units are world cm. Rebuilt from the document after every change."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setSceneRect(SCENE_RECT)
        self.grid_size = 10.0
        self.rooms: list[RoomItem] = []
        self.furniture: list[PlacedItem] = []  # and obstacles
        self.openings: list[OpeningItem] = []
        self.readouts: list[ReadoutItem] = []
        self._extras: list[QGraphicsItem] = []  # handles and clearance zones
        self.preview = PreviewItem()
        self.addItem(self.preview)
        self.preview.clear()

    def clear_plan(self) -> None:
        for item in [*self.rooms, *self.furniture, *self.openings, *self.readouts, *self._extras]:
            self.removeItem(item)
        self.rooms, self.furniture, self.openings, self._extras = [], [], [], []
        self.readouts = []
        self.preview.clear()

    def sync(
        self,
        doc: ProjectDoc,
        selection: frozenset[str],
        *,
        editable: bool,
        hidden: Iterable[str] = (),
        rotate_offset: float = 0.0,
        findings: Sequence[Finding] = (),
    ) -> None:
        """Redraw everything. `rotate_offset` is the rotate handle's distance in cm.

        Items involved in `findings` are outlined in their severity's colour.
        """
        self.clear_plan()
        unit = doc.settings.display_unit
        flags = _flags(findings)
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
                flag=flags.get(room.id),
            )
            self.addItem(item)
            self.rooms.append(item)
        rooms = {room.id: room for room in doc.apartment.rooms}
        for opening in doc.apartment.openings:
            drawn = OpeningItem(rooms[opening.room_id], opening, selected=opening.id in selection)
            self.addItem(drawn)
            self.openings.append(drawn)
        hidden_ids = set(hidden)
        for placed in (*doc.apartment.obstacles, *doc.active_layout.furniture):
            if placed.id not in hidden_ids:
                drawn_item = PlacedItem(
                    placed, unit, selected=placed.id in selection, flag=flags.get(placed.id)
                )
                self.addItem(drawn_item)
                self.furniture.append(drawn_item)
                if isinstance(placed, FurnitureItem) and placed.clearance:
                    zone = ClearanceItem(placed)
                    self.addItem(zone)
                    self._extras.append(zone)
        chosen = selected_placed(doc, selection)
        self._add_readouts(doc, chosen, unit)
        # Obstacles get handles only while the apartment is unlocked; locked furniture none.
        if editable and len(chosen) == 1 and _reshapeable(chosen[0], rooms_editable=handles):
            self._add_handles(chosen[0], rotate_offset)
        if doc.settings.grid_size != self.grid_size:
            self.grid_size = doc.settings.grid_size
            self.update()

    def _add_readouts(self, doc: ProjectDoc, chosen: list[Placed], unit: Unit) -> None:
        """One item: its distance to the walls on each side. Two: the gap between them."""
        segments: list[Segment | None] = []
        if len(chosen) == 1:
            segments = list(wall_gaps(chosen[0], doc.apartment.rooms).values())
        elif len(chosen) == 2:
            segments = [gap_between(*chosen)]
        for segment in segments:
            if segment is not None and math.dist(*segment) > EPS:  # flush: nothing to show
                readout = ReadoutItem(segment, format_length(math.dist(*segment), unit))
                self.addItem(readout)
                self.readouts.append(readout)

    def _add_handles(self, item: Placed, rotate_offset: float) -> None:
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


def _flags(findings: Sequence[Finding]) -> dict[str, Severity]:
    """The worst severity each item is involved in."""
    flags: dict[str, Severity] = {}
    for finding in findings:
        for item_id in finding.ids:
            if flags.get(item_id) != "collision":
                flags[item_id] = finding.severity
    return flags


def _reshapeable(item: Placed, *, rooms_editable: bool) -> bool:
    if isinstance(item, FurnitureItem):
        return not item.locked
    return rooms_editable
