"""Light and dark appearance: the Fusion style with a palette of our own, so the
app looks the same on Windows and macOS (docs/SPEC.md §13)."""

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from apartment_planner.canvas import style

DARK_KEY = "appearance/dark"
Role = QPalette.ColorRole

DARK_DISABLED = "#7b7e83"  # disabled text and buttons
_DARK_COLOURS = {
    Role.Window: "#2b2d31",
    Role.WindowText: "#e2e2dc",
    Role.Base: "#1e1f22",
    Role.AlternateBase: "#26282c",
    Role.ToolTipBase: "#1e1f22",
    Role.ToolTipText: "#e2e2dc",
    Role.PlaceholderText: "#8a8c90",
    Role.Text: "#e2e2dc",
    Role.Button: "#33363b",
    Role.ButtonText: "#e2e2dc",
    Role.BrightText: "#ff6b6b",
    Role.Link: "#5b93f0",
    Role.Highlight: "#3d6fc4",
    Role.HighlightedText: "#ffffff",
    Role.Light: "#45484e",
    Role.Midlight: "#3a3d42",
    Role.Mid: "#2f3236",
    Role.Dark: "#191a1d",
    Role.Shadow: "#000000",
}


def dark_palette() -> QPalette:
    palette = QPalette()
    for role, colour in _DARK_COLOURS.items():
        palette.setColor(role, QColor(colour))
    disabled = QColor(DARK_DISABLED)
    for role in (Role.WindowText, Role.Text, Role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return palette


# The calm look: soft grey section headings and flat chip buttons in the side
# panels, so the plan stays the loudest thing on screen. Only colours no palette
# has are here; the accent is the canvas's, text and chips the window palette's.
_STYLE_COLOURS = {
    False: {"muted": "#6b6f76", "accent_soft": "#e3ecfb", "chip": "#ebebe8",
            "chip_hover": "#dfdfdb", "disabled": "#a5a7ab"},
    True: {"muted": "#9a9da3", "accent_soft": "#2c3a55", "chip": _DARK_COLOURS[Role.Midlight],
           "chip_hover": _DARK_COLOURS[Role.Light], "disabled": DARK_DISABLED},
}  # fmt: skip
_STYLESHEET = """
QToolBar { spacing: 4px; padding: 4px 6px; border: none; }
QToolBar QToolButton { padding: 5px 9px; border-radius: 6px; }
QToolBar QToolButton:hover { background: {chip}; }
QToolBar QToolButton[tool="true"]:checked { background: {accent_soft}; color: {accent}; }
QDockWidget { font-weight: 600; }
QDockWidget::title { padding: 8px 10px 2px 10px; }
QDockWidget > QWidget { font-weight: normal; }
QLabel[heading="true"] { color: {muted}; font-weight: 600; padding: 10px 0 2px 0; }
QDockWidget QToolButton, QDockWidget QPushButton {
    background: {chip}; border: none; border-radius: 6px; padding: 4px 10px;
    color: palette(button-text);
}
QDockWidget QToolButton:hover, QDockWidget QPushButton:hover { background: {chip_hover}; }
QDockWidget QToolButton:disabled, QDockWidget QPushButton:disabled { color: {disabled}; }
QDockWidget QToolButton:checked { background: {accent_soft}; color: {accent}; }
QGroupBox { border: none; margin-top: 18px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 0; color: {muted}; }
"""


def stylesheet(dark: bool) -> str:
    """The app's stylesheet in light or dark colours."""
    text = _STYLESHEET
    accent = (style.DARK if dark else style.LIGHT).accent.name()
    for name, colour in {**_STYLE_COLOURS[dark], "accent": accent}.items():
        text = text.replace("{" + name + "}", colour)
    return text


def system_is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def saved_dark(settings: QSettings) -> bool:
    """The saved choice, or the system's appearance if there's none yet."""
    value = settings.value(DARK_KEY)
    if value is None:
        return system_is_dark()
    return str(value).lower() in ("true", "1")


def apply_theme(app: QApplication, dark: bool) -> None:
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    app.setPalette(dark_palette() if dark else app.style().standardPalette())
    style.use_theme(dark)
