"""Titled sections for the side panels. The app's stylesheet styles them through
their `heading` and `section` properties (docs/SPEC.md §13)."""

from PySide6.QtWidgets import QFrame, QLabel, QLayout, QVBoxLayout, QWidget


def heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("heading", True)
    return label


def section(title: str, content: QWidget | QLayout) -> QFrame:
    """A heading over `content`, in a frame the stylesheet can draw as a card."""
    frame = QFrame()
    frame.setProperty("section", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(heading(title))
    if isinstance(content, QLayout):
        layout.addLayout(content)
    else:
        layout.addWidget(content)
    return frame
