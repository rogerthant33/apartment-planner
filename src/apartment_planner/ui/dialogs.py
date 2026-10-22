"""Modal dialogs, kept behind small functions so tests can replace them."""

from enum import StrEnum
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractButton,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from apartment_planner.persistence.library import name_problem

PROJECT_FILTER = "Apartment Planner projects (*.apartment)"


def error_message(error: Exception) -> str:
    """A message for a failed file operation: our own errors explain themselves."""
    if isinstance(error, OSError):
        return f"{error.strerror or error}. Check that you can change files in that folder."
    return str(error)


def show_error(parent: QWidget | None, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def confirm(parent: QWidget | None, title: str, text: str, action: str) -> bool:
    box = QMessageBox(QMessageBox.Icon.Question, title, text, parent=parent)
    yes = box.addButton(action, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    return box.clickedButton() is yes


def ask_text(parent: QWidget | None, title: str, label: str, text: str = "") -> str | None:
    """A line of text, or None if the user cancels or leaves it empty."""
    value, ok = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Normal, text)
    return (value.strip() or None) if ok else None


def ask_project_name(parent: QWidget | None, title: str, text: str = "") -> str | None:
    """Ask until the name is usable as a file name, or the user cancels."""
    label = "Project name:"
    while True:
        name, ok = QInputDialog.getText(parent, title, label, QLineEdit.EchoMode.Normal, text)
        if not ok:
            return None
        problem = name_problem(name)
        if problem is None:
            return name
        label, text = f"{problem}\nProject name:", name


def open_file(parent: QWidget | None, folder: Path) -> Path | None:
    path, _ = QFileDialog.getOpenFileName(parent, "Open Project", str(folder), PROJECT_FILTER)
    return Path(path) if path else None


def save_file(parent: QWidget | None, title: str, suggested: Path) -> Path | None:
    path, _ = QFileDialog.getSaveFileName(
        parent,
        title,
        str(suggested),
        PROJECT_FILTER,
        options=QFileDialog.Option.DontConfirmOverwrite,  # we never overwrite; see save_copy
    )
    if not path:
        return None
    return Path(path) if path.endswith(".apartment") else Path(path + ".apartment")


def choose_folder(parent: QWidget | None, folder: Path) -> Path | None:
    path = QFileDialog.getExistingDirectory(parent, "Choose Projects Folder", str(folder))
    return Path(path) if path else None


class FailedSaveChoice(StrEnum):
    RETRY = "retry"
    SAVE_COPY = "save_copy"
    DISCARD = "discard"
    CANCEL = "cancel"


def ask_failed_save(parent: QWidget | None, name: str, reason: str) -> FailedSaveChoice:
    box = QMessageBox(
        QMessageBox.Icon.Warning,
        "Unsaved Changes",
        f'The latest changes to "{name}" couldn\'t be saved: {reason}\n\n'
        "Try saving again, save a copy somewhere else, or close without saving them.",
        parent=parent,
    )
    choices: dict[QAbstractButton, FailedSaveChoice] = {
        box.addButton("Try Again", QMessageBox.ButtonRole.AcceptRole): FailedSaveChoice.RETRY,
        box.addButton("Save a Copy…", QMessageBox.ButtonRole.ActionRole): (
            FailedSaveChoice.SAVE_COPY
        ),
        box.addButton("Close Without Saving", QMessageBox.ButtonRole.DestructiveRole): (
            FailedSaveChoice.DISCARD
        ),
        box.addButton(QMessageBox.StandardButton.Cancel): FailedSaveChoice.CANCEL,
    }
    box.exec()
    return choices.get(box.clickedButton(), FailedSaveChoice.CANCEL)
