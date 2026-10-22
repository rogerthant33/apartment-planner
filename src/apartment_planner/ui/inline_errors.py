"""Red messages under a panel's fields, for input that was refused."""

from collections.abc import Callable

from PySide6.QtWidgets import QLabel

from apartment_planner.model import ProjectDoc
from apartment_planner.state.editor import EditorState
from apartment_planner.state.errors import EditError


def error_label() -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    label.setStyleSheet("color: #d32f2f;")
    label.hide()
    return label


def show_error(label: QLabel, message: str | None) -> None:
    label.setText(message or "")
    label.setVisible(message is not None)


def commit_or_refuse(
    state: EditorState,
    label: QLabel,
    change: Callable[[ProjectDoc], ProjectDoc],
    refresh: Callable[[], None],
) -> None:
    """Commit `change(doc)`, or show why it was refused under the fields and put the
    fields back to the document's values with `refresh`."""
    try:
        doc = change(state.doc)
    except EditError as error:
        show_error(label, str(error))
        refresh()
        return
    show_error(label, None)
    state.commit(doc)
