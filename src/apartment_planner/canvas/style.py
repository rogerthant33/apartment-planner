"""Colours and sizes for the plan: a technical drawing, light or dark
(docs/SPEC.md §13).

`colours` is the palette in use. Items read it when they're made; `use_theme`
switches it, and the scene is then rebuilt.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    background: QColor
    grid_minor: QColor
    grid_major: QColor
    room_fill: QColor
    room_outline: QColor
    label: QColor
    label_background: QColor
    furniture_fill: QColor
    furniture_outline: QColor
    obstacle_hatch: QColor
    handle_fill: QColor
    accent: QColor
    invalid: QColor  # reserved for collisions and invalid edits
    warning: QColor  # fit-check warnings
    clearance_fill: QColor
    collision_text: QColor  # findings in the Fit Checks list
    warning_text: QColor


LIGHT = Palette(
    background=QColor("#f6f6f3"),
    grid_minor=QColor("#e7e7e2"),
    grid_major=QColor("#d3d3cc"),
    room_fill=QColor(232, 226, 212, 150),
    room_outline=QColor("#2b2b2b"),
    label=QColor("#3a3a3a"),
    label_background=QColor(255, 255, 255, 170),
    furniture_fill=QColor(203, 196, 184, 210),
    furniture_outline=QColor("#4a453d"),
    obstacle_hatch=QColor("#6d665b"),
    handle_fill=QColor("white"),
    accent=QColor("#2f6fde"),
    invalid=QColor("#d32f2f"),
    warning=QColor("#d98a00"),
    clearance_fill=QColor(47, 111, 222, 28),
    collision_text=QColor("#d32f2f").darker(130),
    warning_text=QColor("#d98a00").darker(130),
)
DARK = Palette(
    background=QColor("#1e1f22"),
    grid_minor=QColor("#2a2b2f"),
    grid_major=QColor("#3a3c41"),
    room_fill=QColor(70, 66, 58, 150),
    room_outline=QColor("#d8d8d2"),
    label=QColor("#e2e2dc"),
    label_background=QColor(30, 31, 34, 190),
    furniture_fill=QColor(104, 98, 88, 220),
    furniture_outline=QColor("#cfc8bb"),
    obstacle_hatch=QColor("#a69f92"),
    handle_fill=QColor("#1e1f22"),
    accent=QColor("#5b93f0"),
    invalid=QColor("#ef5350"),
    warning=QColor("#f0a92a"),
    clearance_fill=QColor(91, 147, 240, 36),
    collision_text=QColor("#ef5350"),
    warning_text=QColor("#f0a92a"),
)

colours = LIGHT

OUTLINE_PX = 2.0
HANDLE_PX = 9
ROTATE_PX = 28  # how far beyond an item's top edge its rotate handle sits
SNAP_PX = 10  # how close on screen a vertex or edge must be to attract the cursor
DRAG_PX = 4  # how far the pointer must move before a press on a room becomes a drag
WALL_PX = 25  # how close to a wall a door or window lands on it
CLOSE_PX = 10  # how close to the first point a click closes a polygon
MIN_GRID_PX = 6  # grid lines closer than this on screen aren't drawn
DIMENSION_PX = 11.0  # how far split wall dimensions sit off the wall line


def is_dark() -> bool:
    return colours is DARK


def use_theme(dark: bool) -> None:
    global colours
    colours = DARK if dark else LIGHT


@contextmanager
def light() -> Iterator[None]:
    """The light colours for a while, e.g. for an export, whatever the screen uses."""
    dark = is_dark()
    use_theme(False)
    try:
        yield
    finally:
        use_theme(dark)
