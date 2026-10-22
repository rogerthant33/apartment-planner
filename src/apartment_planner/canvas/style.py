"""Colours and sizes for the plan: a light technical drawing (docs/SPEC.md §13)."""

from PySide6.QtGui import QColor

BACKGROUND = QColor("#f6f6f3")
GRID_MINOR = QColor("#e7e7e2")
GRID_MAJOR = QColor("#d3d3cc")
ROOM_FILL = QColor(232, 226, 212, 150)
ROOM_OUTLINE = QColor("#2b2b2b")
LABEL = QColor("#3a3a3a")
FURNITURE_FILL = QColor(203, 196, 184, 210)
FURNITURE_OUTLINE = QColor("#4a453d")
OBSTACLE_HATCH = QColor("#6d665b")
ACCENT = QColor("#2f6fde")
INVALID = QColor("#d32f2f")  # reserved for collisions and invalid edits
WARNING = QColor("#d98a00")  # fit-check warnings
CLEARANCE_FILL = QColor(47, 111, 222, 28)

OUTLINE_PX = 2.0
HANDLE_PX = 9
ROTATE_PX = 28  # how far beyond an item's top edge its rotate handle sits
SNAP_PX = 10  # how close on screen a vertex or edge must be to attract the cursor
WALL_PX = 25  # how close to a wall a door or window lands on it
CLOSE_PX = 10  # how close to the first point a click closes a polygon
MIN_GRID_PX = 6  # grid lines closer than this on screen aren't drawn
