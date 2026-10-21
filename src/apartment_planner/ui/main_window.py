from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QWidget,
)

APP_NAME = "Apartment Planner"


class MainWindow(QMainWindow):
    """Application shell: canvas in the centre, tool and property panels at the sides."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 900)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.setCentralWidget(self.view)

        self.tools_panel = self._add_panel("Tools", Qt.DockWidgetArea.LeftDockWidgetArea)
        self.properties_panel = self._add_panel("Properties", Qt.DockWidgetArea.RightDockWidgetArea)

        self.statusBar().showMessage("No project open")

    def _add_panel(self, title: str, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"{title.lower()}_panel")
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setMinimumWidth(240)
        placeholder = QLabel("Nothing here yet.", dock)
        placeholder.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        dock.setWidget(placeholder)
        self.addDockWidget(area, dock)
        return dock
