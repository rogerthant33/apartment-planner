from PySide6.QtCore import QObject, Signal

from apartment_planner.state.editor import EditorState


class EditorSignals(QObject):
    """Qt signals for an EditorState's change notifications."""

    document_changed = Signal()
    selection_changed = Signal()

    def __init__(self, state: EditorState, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = state
        state.on_document_changed(self.document_changed.emit)
        state.on_selection_changed(self.selection_changed.emit)
