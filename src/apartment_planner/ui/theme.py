"""Light and dark appearance: the Fusion style with a palette of our own, so the
app looks the same on Windows and macOS (docs/SPEC.md §13)."""

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from apartment_planner.canvas import style

DARK_KEY = "appearance/dark"
Role = QPalette.ColorRole

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
    disabled = QColor("#7b7e83")
    for role in (Role.WindowText, Role.Text, Role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return palette


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
