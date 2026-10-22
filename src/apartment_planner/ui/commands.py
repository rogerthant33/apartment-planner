"""Edit commands behind the menus, shortcuts and panel buttons.

Each command computes a new document with the pure edit functions and commits
it through EditorState, or tells the user why it can't.
"""

from collections.abc import Callable, Iterable

from apartment_planner.canvas.view import PlanView
from apartment_planner.geometry.shapes import l_shape
from apartment_planner.geometry.snapping import snap_to_grid
from apartment_planner.model import EllipseShape, ProjectDoc, RectShape, Shape
from apartment_planner.state.editor import EditorState
from apartment_planner.state.errors import EditError
from apartment_planner.state.furniture import (
    active_furniture,
    add_furniture,
    duplicate_furniture,
    group_furniture,
    move_furniture,
    rotate_furniture,
    selected_furniture,
    set_locked,
    ungroup_furniture,
    with_groups,
)
from apartment_planner.state.rooms import duplicate_room, selected_room

DUPLICATE_OFFSET = (50.0, 50.0)  # cm, so a copy doesn't hide its original

# What "Add furniture" places: name, category and shape.
FURNITURE_TEMPLATES: dict[str, tuple[str, str | None, Shape]] = {
    "rect": ("Table", "Table", RectShape(width=120, depth=80)),
    "round": ("Round table", "Table", EllipseShape(rx=45, ry=45)),
    "l_shape": (
        "Corner sofa",
        "Seating",
        l_shape(width=250, depth=160, arm_width=90, arm_depth=90),
    ),
}


class Commands:
    def __init__(self, view: PlanView) -> None:
        self.view = view

    @property
    def state(self) -> EditorState | None:
        return self.view.current_state

    def selected_furniture_ids(self) -> frozenset[str]:
        state = self.state
        if state is None:
            return frozenset()
        return frozenset(f.id for f in selected_furniture(state.doc, state.selection))

    def apply(self, change: Callable[[ProjectDoc], ProjectDoc]) -> None:
        """Commit `change(doc)`, or say why it was refused."""
        self.create(lambda doc: (change(doc), None), select=None)

    def create[T](
        self,
        change: Callable[[ProjectDoc], tuple[ProjectDoc, T]],
        select: Callable[[T], Iterable[str]] | None,
    ) -> None:
        """Commit a change that makes something, then select what `select` picks from it."""
        state = self.state
        if state is None or not self.view.editable:
            return
        try:
            doc, made = change(state.doc)
        except EditError as error:
            self.view.notify(str(error))
            return
        state.commit(doc)
        if select is not None:
            state.select(select(made))

    def nudge(self, dx: float, dy: float) -> None:
        ids = self.selected_furniture_ids()
        if ids:
            self.apply(lambda doc: move_furniture(doc, ids, (dx, dy)))

    def rotate(self, degrees: float) -> None:
        ids = self.selected_furniture_ids()
        if ids:
            self.apply(lambda doc: rotate_furniture(doc, ids, degrees))

    def duplicate(self) -> None:
        state = self.state
        if state is None:
            return
        ids = self.selected_furniture_ids()
        if ids:
            self.create(
                lambda doc: duplicate_furniture(doc, ids, DUPLICATE_OFFSET),
                select=lambda copies: copies,
            )
            return
        room = selected_room(state.doc, state.selection)
        if room is not None and self.view.can_edit_rooms():
            self.create(
                lambda doc: duplicate_room(doc, room.id, DUPLICATE_OFFSET),
                select=lambda copy_id: {copy_id},
            )

    def select_all(self) -> None:
        state = self.state
        if state is not None:
            hidden = self.view.hidden
            state.select(f.id for f in active_furniture(state.doc) if f.id not in hidden)

    def group(self) -> None:
        ids = self.selected_furniture_ids()
        self.create(lambda doc: group_furniture(doc, ids), select=lambda _: ids)

    def ungroup(self) -> None:
        ids = self.selected_furniture_ids()
        if ids:
            self.apply(lambda doc: ungroup_furniture(doc, ids))

    def toggle_lock(self) -> None:
        state = self.state
        if state is None:
            return
        items = selected_furniture(state.doc, state.selection)
        if items:
            locked = not all(item.locked for item in items)
            self.apply(lambda doc: set_locked(doc, [i.id for i in items], locked))

    def add(self, template: str) -> None:
        """Place a new item from a template at the centre of the view."""
        state = self.state
        if state is None:
            return
        name, category, shape = FURNITURE_TEMPLATES[template]
        centre = self.view.mapToScene(self.view.viewport().rect().center())
        at = snap_to_grid((centre.x(), centre.y()), state.doc.settings.grid_size)
        self.create(
            lambda doc: add_furniture(doc, shape, at, name, category),
            select=lambda item_id: {item_id},
        )

    def select_with_groups(self, item_id: str) -> None:
        state = self.state
        if state is not None:
            state.select(with_groups(state.doc, {item_id}))
