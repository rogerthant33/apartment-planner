"""Edit commands behind the menus, shortcuts and panel buttons.

Each command computes a new document with the pure edit functions and commits
it through EditorState, or tells the user why it can't.
"""

from collections.abc import Callable, Iterable

from apartment_planner.canvas.view import PlanView
from apartment_planner.geometry.shapes import l_shape
from apartment_planner.geometry.snapping import snap_to_grid
from apartment_planner.model import EllipseShape, FurnitureItem, ProjectDoc, RectShape, Shape
from apartment_planner.state.clipboard import Clip, copy_selection, paste, remove
from apartment_planner.state.editor import EditorState
from apartment_planner.state.errors import EditError
from apartment_planner.state.furniture import (
    active_furniture,
    add_furniture,
    group_furniture,
    selected_furniture,
    set_locked,
    ungroup_furniture,
    with_groups,
)
from apartment_planner.state.placed import (
    add_obstacle,
    duplicate_placed,
    move_placed,
    rotate_placed,
    selected_placed,
)
from apartment_planner.state.rooms import copy_rooms, selected_rooms

DUPLICATE_OFFSET = (50.0, 50.0)  # cm, so a copy doesn't hide its original

# What "Add obstacle" places: name and shape.
OBSTACLE_TEMPLATES: dict[str, tuple[str, Shape]] = {
    "column": ("Column", RectShape(width=30, depth=30)),
    "radiator": ("Radiator", RectShape(width=100, depth=10)),
    "cupboard": ("Built-in cupboard", RectShape(width=120, depth=60)),
}

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
        self.clip: Clip | None = None  # what Ctrl+C or Ctrl+X took, for Ctrl+V
        # How many offsets on the next paste lands: each paste a step further on, the
        # first after a copy one step, and the first after a cut back in place.
        self._paste_step = 1

    @property
    def state(self) -> EditorState | None:
        return self.view.current_state

    def selected_furniture_ids(self) -> frozenset[str]:
        state = self.state
        if state is None:
            return frozenset()
        return frozenset(f.id for f in selected_furniture(state.doc, state.selection))

    def selected_placed_ids(self) -> frozenset[str]:
        """Selected furniture, or selected obstacles while the apartment can be edited."""
        state = self.state
        if state is None:
            return frozenset()
        items = selected_placed(state.doc, state.selection)
        if any(not isinstance(i, FurnitureItem) for i in items) and not self.view.can_edit_rooms():
            return frozenset()
        return frozenset(i.id for i in items)

    def apply(self, change: Callable[[ProjectDoc], ProjectDoc]) -> bool:
        """Commit `change(doc)`, or say why it was refused. True if it was committed."""
        return self.create(lambda doc: (change(doc), None), select=None)

    def create[T](
        self,
        change: Callable[[ProjectDoc], tuple[ProjectDoc, T]],
        select: Callable[[T], Iterable[str]] | None,
    ) -> bool:
        """Commit a change that makes something, then select what `select` picks from it.
        True if it was committed; False if it was refused (and the user told why)."""
        state = self.state
        if state is None or not self.view.editable:
            return False
        try:
            doc, made = change(state.doc)
        except EditError as error:
            self.view.notify(str(error))
            return False
        state.commit(doc)
        if select is not None:
            state.select(select(made))
        return True

    def nudge(self, dx: float, dy: float) -> None:
        ids = self.selected_placed_ids()
        if ids:
            self.apply(lambda doc: move_placed(doc, ids, (dx, dy)))

    def rotate(self, degrees: float) -> None:
        ids = self.selected_placed_ids()
        if ids:
            self.apply(lambda doc: rotate_placed(doc, ids, degrees))

    def duplicate(self) -> None:
        state = self.state
        if state is None:
            return
        ids = self.selected_placed_ids()
        if ids:
            self.create(
                lambda doc: duplicate_placed(doc, ids, DUPLICATE_OFFSET),
                select=lambda copies: copies,
            )
            return
        rooms = selected_rooms(state.doc, state.selection)
        if rooms and self.view.can_edit_rooms():
            self.create(
                lambda doc: copy_rooms(doc, rooms, doc.apartment.openings, DUPLICATE_OFFSET),
                select=lambda copies: copies,
            )
        elif state.selection and not self.view.can_edit_rooms():
            self.view.notify("The apartment is locked. Unlock it to duplicate rooms or obstacles.")
        else:
            self.view.notify("Select furniture, obstacles or rooms to duplicate them.")

    def copy(self) -> Clip | None:
        """Put copies of the selection on the clipboard, and return them."""
        state = self.state
        clip = copy_selection(state.doc, state.selection) if state is not None else None
        if clip is None:
            self.view.notify("Select furniture, obstacles or rooms to copy them.")
            return None
        self.clip, self._paste_step = clip, 1
        return clip

    def cut(self) -> None:
        clip = self.copy()
        if clip is None:
            return
        if clip.is_apartment and not self.view.can_edit_rooms():
            self.view.notify("They were copied but not cut: unlock the apartment to cut them.")
            return
        if self.apply(lambda doc: remove(doc, clip)):  # refused for locked items: only copied
            self._paste_step = 0

    def paste(self) -> None:
        clip = self.clip
        if clip is None or self.state is None:
            return
        if clip.is_apartment and not self.view.can_edit_rooms():
            self.view.notify("Unlock the apartment to paste rooms or obstacles.")
            return
        step = self._paste_step
        offset = (DUPLICATE_OFFSET[0] * step, DUPLICATE_OFFSET[1] * step)
        if self.create(lambda doc: paste(doc, clip, offset), select=lambda pasted: pasted):
            self._paste_step += 1

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

    def add_obstacle(self, template: str) -> None:
        """Place a new obstacle at the centre of the view. Needs an unlocked apartment."""
        state = self.state
        if state is None or not self.view.can_edit_rooms():
            return
        name, shape = OBSTACLE_TEMPLATES[template]
        centre = self.view.mapToScene(self.view.viewport().rect().center())
        at = snap_to_grid((centre.x(), centre.y()), state.doc.settings.grid_size)
        self.create(lambda doc: add_obstacle(doc, shape, at, name), select=lambda new: {new})

    def select_with_groups(self, item_id: str) -> None:
        state = self.state
        if state is not None:
            state.select(with_groups(state.doc, {item_id}))
