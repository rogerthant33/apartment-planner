"""Red messages under a panel's fields, for input that was refused."""

from PySide6.QtWidgets import QLabel


def error_label() -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    label.setStyleSheet("color: #d32f2f;")
    label.hide()
    return label


def show_error(label: QLabel, message: str | None) -> None:
    label.setText(message or "")
    label.setVisible(message is not None)
