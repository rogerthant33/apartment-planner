import sys

from PySide6.QtWidgets import QApplication

from apartment_planner.ui.main_window import APP_NAME, MainWindow


def configure_application(app: QApplication) -> None:
    """Fusion style; the window picks light or dark (docs/SPEC.md §13)."""
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")


def run() -> int:
    app = QApplication(sys.argv)
    configure_application(app)
    window = MainWindow()
    window.show()
    return app.exec()
