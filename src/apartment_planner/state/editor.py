"""The document being edited, the selection and undo history. See docs/SPEC.md §12.

Pure Python. The Qt layer observes it through `canvas.signals.EditorSignals`.
"""

from collections.abc import Callable, Iterable

from apartment_planner.model import ProjectDoc

HISTORY_LIMIT = 200

Listener = Callable[[], None]


def keep_untracked(restored: ProjectDoc, current: ProjectDoc) -> ProjectDoc:
    """`restored` with the current values of what undo and redo leave alone.

    The project name, its settings (including the apartment lock) and the
    active layout are not part of the edit history.
    """
    layout_ids = {layout.id for layout in restored.layouts}
    active = current.active_layout_id
    return restored.evolve(
        name=current.name,
        settings=current.settings,
        active_layout_id=active if active in layout_ids else restored.active_layout_id,
    )


class EditorState:
    """Every committed edit replaces the document; the previous one goes on the
    undo stack. Documents are immutable, so the stack shares unchanged parts.
    """

    def __init__(self, doc: ProjectDoc) -> None:
        self._doc = doc
        self._selection: frozenset[str] = frozenset()
        self._undo: list[ProjectDoc] = []
        self._redo: list[ProjectDoc] = []
        self.revision = 0
        self._document_listeners: list[Listener] = []
        self._selection_listeners: list[Listener] = []

    @property
    def doc(self) -> ProjectDoc:
        return self._doc

    @property
    def selection(self) -> frozenset[str]:
        return self._selection

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def on_document_changed(self, listener: Listener) -> None:
        self._document_listeners.append(listener)

    def on_selection_changed(self, listener: Listener) -> None:
        self._selection_listeners.append(listener)

    def commit(self, doc: ProjectDoc) -> None:
        """Make `doc` current as one undoable step. Committing an equal document does nothing."""
        if doc == self._doc:
            return
        self._undo.append(self._doc)
        del self._undo[:-HISTORY_LIMIT]
        self._redo.clear()
        self._replace(doc)

    def update_untracked(self, doc: ProjectDoc) -> None:
        """Change something undo doesn't cover (see `keep_untracked`), keeping history."""
        if doc != self._doc:
            self._replace(doc)

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self._doc)
            self._replace(keep_untracked(self._undo.pop(), self._doc))

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self._doc)
            self._replace(keep_untracked(self._redo.pop(), self._doc))

    def select(self, ids: Iterable[str]) -> None:
        selection = frozenset(ids)
        if selection != self._selection:
            self._selection = selection
            self._notify(self._selection_listeners)

    def _replace(self, doc: ProjectDoc) -> None:
        self._doc = doc
        self.revision += 1
        # Drop selected things that no longer exist, e.g. after undoing their creation.
        stale = self._selection - set(doc.all_ids())
        self._selection -= stale
        self._notify(self._document_listeners)
        if stale:
            self._notify(self._selection_listeners)

    @staticmethod
    def _notify(listeners: list[Listener]) -> None:
        for listener in listeners:
            listener()
