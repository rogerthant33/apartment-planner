from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from apartment_planner.persistence.errors import ProjectFileError
from apartment_planner.persistence.library import Library, create_project, project_name
from apartment_planner.persistence.session import ProjectSession
from apartment_planner.ui import dialogs
from apartment_planner.ui.dialogs import FailedSaveChoice, error_message
from apartment_planner.ui.open_project import OpenProject, local_now
from apartment_planner.ui.reveal import show_in_folder
from apartment_planner.ui.start_screen import StartScreen

APP_NAME = "Apartment Planner"
GEOMETRY_KEY = "window/geometry"


class Banner(QFrame):
    """A message across the top of the editor, with an optional action button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("Banner { background: #fff4d6; border-bottom: 1px solid #e0c97a; }")
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.button = QPushButton()
        self.button.clicked.connect(self._trigger)
        dismiss = QPushButton("Dismiss")
        dismiss.clicked.connect(self.hide)
        layout = QHBoxLayout(self)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.button)
        layout.addWidget(dismiss)
        self._action: QAction | None = None
        self.hide()

    def show_message(self, text: str, action: QAction | None = None) -> None:
        self.label.setText(text)
        self._action = action
        self.button.setVisible(action is not None)
        if action is not None:
            self.button.setText(action.text())
        self.show()

    def _trigger(self) -> None:
        if self._action is not None:
            self._action.trigger()


class MainWindow(QMainWindow):
    """The start screen when no project is open, otherwise the editor."""

    def __init__(self, settings: QSettings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings()
        self.library = Library(self.settings)
        self.project: OpenProject | None = None
        self.resize(1400, 900)

        self.start_screen = StartScreen(self.library)
        self.start_screen.open_requested.connect(self.open_path)
        self.start_screen.new_requested.connect(self.new_project)
        self.start_screen.browse_requested.connect(self.browse)

        self.banner = Banner()
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self.banner)
        editor_layout.addWidget(self.view, 1)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.start_screen)
        self.pages.addWidget(editor)
        self.setCentralWidget(self.pages)

        self.tools_panel = self._add_panel("Tools", Qt.DockWidgetArea.LeftDockWidgetArea)
        self.properties_panel = self._add_panel("Properties", Qt.DockWidgetArea.RightDockWidgetArea)

        self.save_status = QLabel()
        self.statusBar().addPermanentWidget(self.save_status)

        self._create_actions()
        self._create_menus()
        geometry = self.settings.value(GEOMETRY_KEY)
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        self._show_start_screen()

    # Project lifecycle

    def new_project(self) -> None:
        name = dialogs.ask_project_name(self, "New Project")
        if name is None or not self.close_project():
            return
        try:
            project, session = create_project(self.library.folder, name, local_now())
        except (ProjectFileError, OSError) as error:
            dialogs.show_error(self, "Couldn't Create Project", error_message(error))
            return
        self._show_project(OpenProject(session, project))

    def browse(self) -> None:
        path = dialogs.open_file(self, self.library.folder)
        if path is not None:
            self.open_path(path)

    def open_path(self, path: Path) -> bool:
        if not self.close_project():
            return False
        try:
            project, session = ProjectSession.open(path)
        except (ProjectFileError, OSError) as error:
            if not path.exists():
                self.library.remove_recent(path)
                self.start_screen.refresh()
            dialogs.show_error(self, "Couldn't Open Project", error_message(error))
            return False
        self._show_project(OpenProject(session, project))
        return True

    def close_project(self) -> bool:
        """Save and close the open project. False if the user chose to keep it open."""
        project = self.project
        if project is None:
            return True
        while not project.flush():
            choice = dialogs.ask_failed_save(self, project.name, project.save_error or "")
            if choice is FailedSaveChoice.CANCEL:
                return False
            if choice is FailedSaveChoice.DISCARD:
                break
            if choice is FailedSaveChoice.SAVE_COPY and self.save_copy() is not None:
                break
        project.close()
        project.deleteLater()
        self.project = None
        self._show_start_screen()
        return True

    def save_now(self) -> None:
        if self.project is not None and self.project.flush():
            self.statusBar().showMessage("Saved", 2000)

    def save_copy(self) -> Path | None:
        project = self.project
        if project is None:
            return None
        suggested = self.library.folder / f"{project.name} copy.apartment"
        path = dialogs.save_file(self, "Save a Copy As", suggested)
        if path is None:
            return None
        try:
            project.save_copy(path)
        except (ProjectFileError, OSError) as error:
            dialogs.show_error(self, "Couldn't Save a Copy", error_message(error))
            return None
        self.library.add_recent(path)
        self.statusBar().showMessage(f'Saved a copy as "{project_name(path)}"', 5000)
        return path

    def save_editable_copy(self) -> None:
        """For a read-only project: save a copy and continue in it."""
        copy = self.save_copy()
        if copy is not None:
            self.open_path(copy)

    def rename_project(self) -> None:
        project = self.project
        if project is None:
            return
        name = dialogs.ask_project_name(self, "Rename Project", project.name)
        if name is None or name == project.name:
            return
        try:
            project.rename(name)
        except (ProjectFileError, OSError) as error:
            dialogs.show_error(self, "Couldn't Rename Project", error_message(error))

    def show_in_folder(self) -> None:
        if self.project is not None:
            show_in_folder(self.project.path)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.close_project():
            event.ignore()
            return
        self.settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        event.accept()

    # Window state

    def _show_project(self, project: OpenProject) -> None:
        self.project = project
        project.setParent(self)
        project.status_changed.connect(self._update_status)
        project.renamed.connect(self._project_renamed)
        project.conflict.connect(self._show_conflict)
        self.library.add_recent(project.path)
        self.banner.hide()
        if project.read_only_reason is not None:
            self.banner.show_message(project.read_only_reason, self.save_editable_copy_action)
        self.pages.setCurrentIndex(1)
        self._update_window()

    def _show_start_screen(self) -> None:
        self.pages.setCurrentIndex(0)
        self.start_screen.refresh()
        self._update_window()

    def _project_renamed(self, old: Path) -> None:
        if self.project is not None:
            self.library.replace_recent(old, self.project.path)
        self._update_window()

    def _show_conflict(self, original: Path, copy: Path) -> None:
        self.library.add_recent(copy)
        self._update_window()
        self.banner.show_message(
            f'"{project_name(original)}" was changed by someone else while you had it open, '
            f'so your changes were saved to "{project_name(copy)}" instead. You\'re now working '
            "in that copy: compare the two and delete the one you don't need."
        )

    def _update_window(self) -> None:
        project = self.project
        editable = project is not None and project.read_only_reason is None
        self.tools_panel.setVisible(project is not None)
        self.properties_panel.setVisible(project is not None)
        for action in (self.close_action, self.save_copy_action, self.show_in_folder_action):
            action.setEnabled(project is not None)
        for action in (self.save_action, self.rename_action):
            action.setEnabled(editable)
        if project is None:
            self.setWindowTitle(APP_NAME)
        else:
            read_only = "" if editable else " (read-only)"
            self.setWindowTitle(f"{project.name}{read_only} — {APP_NAME}")
        self._update_status()

    def _update_status(self) -> None:
        text, tooltip = self.project.status() if self.project else ("No project open", "")
        self.save_status.setText(text)
        self.save_status.setToolTip(tooltip)

    # Menus

    def _create_actions(self) -> None:
        def action(
            text: str, slot: object, shortcut: QKeySequence.StandardKey | None = None
        ) -> QAction:
            created = QAction(text, self)
            created.triggered.connect(slot)
            if shortcut is not None:
                created.setShortcut(shortcut)
            return created

        self.new_action = action("New…", self.new_project, QKeySequence.StandardKey.New)
        self.open_action = action("Open…", self.browse, QKeySequence.StandardKey.Open)
        self.save_action = action("Save Now", self.save_now, QKeySequence.StandardKey.Save)
        self.save_copy_action = action("Save a Copy As…", self.save_copy)
        self.save_editable_copy_action = action("Save an Editable Copy…", self.save_editable_copy)
        self.rename_action = action("Rename…", self.rename_project)
        self.show_in_folder_action = action("Show in Folder", self.show_in_folder)
        self.export_action = action("Export Plan…", lambda: None)
        self.export_action.setEnabled(False)  # milestone 7
        self.close_action = action("Close", self.close_project, QKeySequence.StandardKey.Close)
        self.quit_action = action("Quit", self.close, QKeySequence.StandardKey.Quit)
        self.quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.about_action = action(f"About {APP_NAME}", self._about)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([self.new_action, self.open_action])
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        file_menu.addSeparator()
        file_menu.addActions([self.save_action, self.save_copy_action, self.rename_action])
        file_menu.addAction(self.show_in_folder_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addActions([self.close_action, self.quit_action])
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.about_action)

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.library.recent()
        for path in recent:
            entry = self.recent_menu.addAction(project_name(path))
            entry.setToolTip(str(path))
            entry.triggered.connect(lambda _=False, p=path: self.open_path(p))
        if not recent:
            self.recent_menu.addAction("No recent projects").setEnabled(False)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME}\n\nPlan your apartment with real measurements and try furniture layouts.",
        )

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
