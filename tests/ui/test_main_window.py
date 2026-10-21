from pytestqt.qtbot import QtBot

from apartment_planner.ui.main_window import APP_NAME, MainWindow


def test_main_window_opens_with_panels_and_status(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == APP_NAME
    assert window.tools_panel.isVisible()
    assert window.properties_panel.isVisible()
    assert window.statusBar().currentMessage() == "No project open"
