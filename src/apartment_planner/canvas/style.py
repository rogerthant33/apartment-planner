"""Colours and sizes for the plan: a technical drawing, light or dark
(docs/SPEC.md §13).

The colours are module attributes so items read the current theme when they're
made; `use_theme` switches them, and the scene is then rebuilt.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtGui import QColor

LIGHT = {
    "BACKGROUND": QColor("#f6f6f3"),
    "GRID_MINOR": QColor("#e7e7e2"),
    "GRID_MAJOR": QColor("#d3d3cc"),
    "ROOM_FILL": QColor(232, 226, 212, 150),
    "ROOM_OUTLINE": QColor("#2b2b2b"),
    "LABEL": QColor("#3a3a3a"),
    "LABEL_BACKGROUND": QColor(255, 255, 255, 170),
    "FURNITURE_FILL": QColor(203, 196, 184, 210),
    "FURNITURE_OUTLINE": QColor("#4a453d"),
    "OBSTACLE_HATCH": QColor("#6d665b"),
    "HANDLE_FILL": QColor("white"),
    "ACCENT": QColor("#2f6fde"),
    "INVALID": QColor("#d32f2f"),  # reserved for collisions and invalid edits
    "WARNING": QColor("#d98a00"),  # fit-check warnings
    "CLEARANCE_FILL": QColor(47, 111, 222, 28),
}
DARK = {
    "BACKGROUND": QColor("#1e1f22"),
    "GRID_MINOR": QColor("#2a2b2f"),
    "GRID_MAJOR": QColor("#3a3c41"),
    "ROOM_FILL": QColor(70, 66, 58, 150),
    "ROOM_OUTLINE": QColor("#d8d8d2"),
    "LABEL": QColor("#e2e2dc"),
    "LABEL_BACKGROUND": QColor(30, 31, 34, 190),
    "FURNITURE_FILL": QColor(104, 98, 88, 220),
    "FURNITURE_OUTLINE": QColor("#cfc8bb"),
    "OBSTACLE_HATCH": QColor("#a69f92"),
    "HANDLE_FILL": QColor("#1e1f22"),
    "ACCENT": QColor("#5b93f0"),
    "INVALID": QColor("#ef5350"),
    "WARNING": QColor("#f0a92a"),
    "CLEARANCE_FILL": QColor(91, 147, 240, 36),
}

BACKGROUND = LIGHT["BACKGROUND"]
GRID_MINOR = LIGHT["GRID_MINOR"]
GRID_MAJOR = LIGHT["GRID_MAJOR"]
ROOM_FILL = LIGHT["ROOM_FILL"]
ROOM_OUTLINE = LIGHT["ROOM_OUTLINE"]
LABEL = LIGHT["LABEL"]
LABEL_BACKGROUND = LIGHT["LABEL_BACKGROUND"]
FURNITURE_FILL = LIGHT["FURNITURE_FILL"]
FURNITURE_OUTLINE = LIGHT["FURNITURE_OUTLINE"]
OBSTACLE_HATCH = LIGHT["OBSTACLE_HATCH"]
HANDLE_FILL = LIGHT["HANDLE_FILL"]
ACCENT = LIGHT["ACCENT"]
INVALID = LIGHT["INVALID"]
WARNING = LIGHT["WARNING"]
CLEARANCE_FILL = LIGHT["CLEARANCE_FILL"]

OUTLINE_PX = 2.0
HANDLE_PX = 9
ROTATE_PX = 28  # how far beyond an item's top edge its rotate handle sits
SNAP_PX = 10  # how close on screen a vertex or edge must be to attract the cursor
WALL_PX = 25  # how close to a wall a door or window lands on it
CLOSE_PX = 10  # how close to the first point a click closes a polygon
MIN_GRID_PX = 6  # grid lines closer than this on screen aren't drawn
DIMENSION_PX = 11.0  # how far split wall dimensions sit off the wall line


_dark = False


def is_dark() -> bool:
    return _dark


def use_theme(dark: bool) -> None:
    global _dark
    _dark = dark
    globals().update(DARK if dark else LIGHT)


@contextmanager
def light() -> Iterator[None]:
    """The light colours for a while, e.g. for an export, whatever the screen uses."""
    dark = is_dark()
    use_theme(False)
    try:
        yield
    finally:
        use_theme(dark)
