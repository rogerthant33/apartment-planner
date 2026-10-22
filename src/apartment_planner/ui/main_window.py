from collections.abc import Callable
from functools import partial
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from apartment_planner.canvas.view import PlanView
from apartment_planner.persistence.errors import ProjectFileError
from apartment_planner.persistence.library import Library, create_project, project_name
from apartment_planner.persistence.session import ProjectSession
from apartment_planner.state.editor import EditorState
from apartment_planner.state.furniture import (
    add_layout,
    delete_layout,
    duplicate_layout,
    rename_layout,
    selected_furniture,
)
from apartment_planner.state.openings import selected_openings
from apartment_planner.state.placed import selectable, selected_obstacles
from apartment_planner.state.rooms import selected_room
from apartment_planner.ui import dialogs
from apartment_planner.ui.commands import Commands
from apartment_planner.ui.dialogs import FailedSaveChoice, error_message
from apartment_planner.ui.findings_panel import FindingsPanel
from apartment_planner.ui.open_project import OpenProject, local_now
from apartment_planner.ui.panels import PropertiesPanel, ToolsPanel
from apartment_planner.ui.reveal import show_in_folder
from apartment_planner.ui.start_screen import StartScreen

APP_NAME = "Apartment Planner"
GEOMETRY_KEY = "window/geometry"
DUPLICATE_OFFSET = (50.0, 50.0)  # cm, so a duplicated room doesn't hide its original
MESSAGE_MS = 8000


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
        self.view = PlanView()
        self.view.message.connect(lambda text: self.statusBar().showMessage(text, MESSAGE_MS))
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

        self.save_status = QLabel()
        self.statusBar().addPermanentWidget(self.save_status)

        self.commands = Commands(self.view)
        self._create_actions()
        self.tools = ToolsPanel(
            self.tool_actions.actions()[:3],
            [*self.tool_actions.actions()[3:], *self.obstacle_actions],
            self.add_actions,
            self.layout_actions,
        )
        self.tools.room_activated.connect(self._select_room)
        self.tools.furniture_activated.connect(self.commands.select_with_groups)
        self.tools.visibility_changed.connect(self.view.set_hidden)
        self.tools.layout_chosen.connect(self.choose_layout)
        self.properties = PropertiesPanel()
        pages = self.properties
        for buttons in (pages.furniture_page.buttons, pages.selection_page.buttons):
            buttons["Duplicate"].clicked.connect(self.commands.duplicate)
            buttons["Delete"].clicked.connect(self.view.delete_selection)
        pages.selection_page.buttons["Group"].clicked.connect(self.commands.group)
        pages.selection_page.buttons["Ungroup"].clicked.connect(self.commands.ungroup)
        pages.selection_page.buttons["Lock"].clicked.connect(self.commands.toggle_lock)
        pages.selection_page.buttons["Unlock"].clicked.connect(self.commands.toggle_lock)
        pages.room_page.duplicate.clicked.connect(self.commands.duplicate)
        pages.room_page.delete.clicked.connect(self.view.delete_selection)
        pages.opening_page.buttons["Delete"].clicked.connect(self.view.delete_selection)
        left, right = Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea
        self.tools_panel = self._add_panel("Tools", left, self.tools)
        self.properties_panel = self._add_panel("Properties", right, self.properties)
        self.findings = FindingsPanel()
        self.findings.finding_activated.connect(self._select_finding)
        self.findings_panel = self._add_panel("Fit Checks", right, self.findings)
        self._create_menus()
        self._create_toolbar()
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
        self.view.set_state(None, editable=False)
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

    # Editing

    @property
    def editor(self) -> EditorState | None:
        return self.project.editor if self.project is not None else None

    def set_tool(self, name: str) -> None:
        self.view.set_tool(name)
        self.tool_actions.actions()[list(self.view.tools).index(name)].setChecked(True)
        self.view.setFocus()

    def undo(self) -> None:
        if self.editor is not None:
            self.view.tool.cancel()
            self.editor.undo()

    def redo(self) -> None:
        if self.editor is not None:
            self.view.tool.cancel()
            self.editor.redo()

    def delete_pressed(self) -> None:
        # While drawing a polygon, Backspace removes the last corner instead.
        if self.editor is not None and not self.view.tool.key(Qt.Key.Key_Backspace):
            self.view.delete_selection()

    def cancel(self) -> None:
        if self.editor is not None and not self.view.tool.key(Qt.Key.Key_Escape):
            self.editor.select(())

    def set_apartment_locked(self, locked: bool) -> None:
        state = self.editor
        if state is None or state.doc.settings.apartment_locked == locked:
            return
        settings = state.doc.settings.evolve(apartment_locked=locked)
        state.update_untracked(state.doc.evolve(settings=settings))
        if locked:
            if self.view.tool not in (self.view.tools["select"], self.view.tools["polygon"]):
                self.set_tool("select")  # the other tools edit the apartment
            state.select(f.id for f in selected_furniture(state.doc, state.selection))

    def shortcut(self, command: Callable[[], None]) -> Callable[[], None]:
        """`command`, except while a text field has focus (it gets the keys instead)."""

        def run() -> None:
            if not isinstance(QApplication.focusWidget(), (QLineEdit, QAbstractSpinBox)):
                command()

        return run

    # Layouts. Switching isn't undoable; the other layout edits are.

    def choose_layout(self, layout_id: str) -> None:
        state = self.editor
        if state is not None and layout_id != state.doc.active_layout_id:
            self.view.tool.cancel()
            state.update_untracked(state.doc.evolve(active_layout_id=layout_id))
            state.select(())

    def add_layout(self) -> None:
        self.commands.create(add_layout, select=lambda _: ())
        self._switch_to_last_layout()

    def duplicate_layout(self) -> None:
        state = self.editor
        if state is not None:
            layout_id = state.doc.active_layout_id
            self.commands.create(lambda doc: duplicate_layout(doc, layout_id), select=lambda _: ())
            self._switch_to_last_layout()

    def rename_layout(self) -> None:
        state = self.editor
        if state is None:
            return
        layout = state.doc.active_layout
        name = dialogs.ask_text(self, "Rename Layout", "Layout name:", layout.name)
        if name is not None:
            self.commands.apply(lambda doc: rename_layout(doc, layout.id, name))

    def delete_layout(self) -> None:
        state = self.editor
        if state is None:
            return
        layout = state.doc.active_layout
        question = f'Delete the layout "{layout.name}" and its {len(layout.furniture)} items?'
        if dialogs.confirm(self, "Delete Layout", question, "Delete"):
            state.select(())
            self.commands.apply(lambda doc: delete_layout(doc, layout.id))

    def _switch_to_last_layout(self) -> None:
        state = self.editor
        if state is not None:
            self.choose_layout(state.doc.layouts[-1].id)

    def set_snapping(self, enabled: bool) -> None:
        state = self.editor
        if state is not None and state.doc.settings.snap_enabled != enabled:
            settings = state.doc.settings.evolve(snap_enabled=enabled)
            state.update_untracked(state.doc.evolve(settings=settings))

    def _select_room(self, room_id: str) -> None:
        if self.editor is not None and not self.editor.doc.settings.apartment_locked:
            self.editor.select({room_id})

    def _select_finding(self, ids: tuple[str, ...]) -> None:
        if self.editor is not None:
            editable = self.view.can_edit_rooms()
            self.editor.select(selectable(self.editor.doc, ids, apartment_editable=editable))

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
        project.signals.document_changed.connect(self._refresh_editor)
        project.signals.selection_changed.connect(self._refresh_editor)
        self.library.add_recent(project.path)
        self.banner.hide()
        if project.read_only_reason is not None:
            self.banner.show_message(project.read_only_reason, self.save_editable_copy_action)
        self.view.set_state(project.editor, editable=project.read_only_reason is None)
        self.set_tool("select")
        self.pages.setCurrentIndex(1)
        self._update_window()
        self.view.zoom_to_fit()

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

    def _refresh_editor(self) -> None:
        state = self.editor
        if state is None:
            return
        self.view.refresh()
        self.tools.refresh(state.doc, state.selection, self.view.hidden)
        self.properties.refresh(state, self.view.editable)
        self.findings.show_findings(self.view.findings)
        self._update_edit_actions()

    def _update_edit_actions(self) -> None:
        state = self.editor
        editable = state is not None and self.view.editable
        rooms = state is not None and self.view.can_edit_rooms()
        has_room = state is not None and selected_room(state.doc, state.selection) is not None
        furniture = selected_furniture(state.doc, state.selection) if state else []
        obstacles = state is not None and bool(selected_obstacles(state.doc, state.selection))
        openings = state is not None and bool(selected_openings(state.doc, state.selection))
        locked = state is not None and state.doc.settings.apartment_locked
        self.undo_action.setEnabled(editable and state is not None and state.can_undo)
        self.redo_action.setEnabled(editable and state is not None and state.can_redo)
        for action in (self.rect_tool_action, *self.opening_tool_actions, *self.obstacle_actions):
            action.setEnabled(rooms)
        self.polygon_tool_action.setEnabled(editable)
        self.polygon_tool_action.setText("Custom Shape" if locked else "Polygon Room")
        apartment = rooms and (has_room or obstacles)
        self.duplicate_action.setEnabled(editable and (bool(furniture) or apartment))
        self.delete_action.setEnabled(editable and (bool(furniture) or apartment or openings))
        for action in (*self.furniture_actions, *self.add_actions, *self.layout_actions):
            action.setEnabled(editable)
        self.select_all_action.setEnabled(state is not None)
        self.lock_action.setEnabled(editable)
        self.snap_action.setEnabled(editable)
        for action in (self.lock_action, self.snap_action):
            action.blockSignals(True)
        self.lock_action.setChecked(state is not None and state.doc.settings.apartment_locked)
        self.snap_action.setChecked(state is not None and state.doc.settings.snap_enabled)
        for action in (self.lock_action, self.snap_action):
            action.blockSignals(False)
        for action in (self.zoom_in_action, self.zoom_out_action, self.zoom_fit_action):
            action.setEnabled(state is not None)

    def _update_window(self) -> None:
        project = self.project
        editable = project is not None and project.read_only_reason is None
        self.tools_panel.setVisible(project is not None)
        self.properties_panel.setVisible(project is not None)
        self.findings_panel.setVisible(project is not None)
        self.toolbar.setVisible(project is not None)
        for action in (self.close_action, self.save_copy_action, self.show_in_folder_action):
            action.setEnabled(project is not None)
        for action in (self.save_action, self.rename_action):
            action.setEnabled(editable)
        self._refresh_editor()
        self._update_edit_actions()
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
            text: str, slot: object, shortcut: QKeySequence.StandardKey | str | None = None
        ) -> QAction:
            created = QAction(text, self)
            created.triggered.connect(slot)
            if shortcut is not None:
                created.setShortcut(shortcut)
            return created

        self.undo_action = action("Undo", self.undo, QKeySequence.StandardKey.Undo)
        self.redo_action = action("Redo", self.redo)
        redo_keys = [
            *QKeySequence.keyBindings(QKeySequence.StandardKey.Redo),
            QKeySequence("Ctrl+Y"),
        ]
        self.redo_action.setShortcuts(list(dict.fromkeys(redo_keys)))
        self.delete_action = action("Delete", self.delete_pressed)
        self.delete_action.setShortcuts([QKeySequence("Delete"), QKeySequence("Backspace")])
        self.duplicate_action = action("Duplicate", self.commands.duplicate, "Ctrl+D")
        self.cancel_action = action("Cancel", self.cancel, "Escape")
        self.addAction(self.cancel_action)  # a shortcut only, not in a menu

        self.tool_actions = QActionGroup(self)
        for name, text, key in (
            ("select", "Select", "V"),
            ("rect", "Rectangle Room", "M"),
            ("polygon", "Polygon Room", "P"),  # a custom shape while the apartment is locked
            ("door", "Door", "D"),
            ("window", "Window", "W"),
            ("opening", "Opening", "O"),
        ):
            tool = action(text, lambda _=False, n=name: self.set_tool(n), key)
            tool.setCheckable(True)
            tool.setToolTip(f"{text} ({key})")
            self.tool_actions.addAction(tool)
        self.select_tool_action, self.rect_tool_action, self.polygon_tool_action = (
            self.tool_actions.actions()[:3]
        )
        self.opening_tool_actions = self.tool_actions.actions()[3:]
        self.lock_action = QAction("Apartment Locked", self)
        self.lock_action.setCheckable(True)
        self.lock_action.setToolTip("While locked, rooms can't be selected or changed")
        self.lock_action.toggled.connect(self.set_apartment_locked)
        self.snap_action = QAction("Snap to Grid and Rooms", self)
        self.snap_action.setCheckable(True)
        self.snap_action.setToolTip("Hold Alt while dragging to suspend snapping")
        self.snap_action.toggled.connect(self.set_snapping)
        self.zoom_in_action = action(
            "Zoom In", lambda: self.view.zoom_by(1.25), QKeySequence.StandardKey.ZoomIn
        )
        self.zoom_out_action = action(
            "Zoom Out", lambda: self.view.zoom_by(0.8), QKeySequence.StandardKey.ZoomOut
        )
        self.zoom_fit_action = action("Zoom to Fit", self.view.zoom_to_fit, "0")

        commands = self.commands
        self.select_all_action = action(
            "Select All Furniture", commands.select_all, QKeySequence.StandardKey.SelectAll
        )
        self.group_action = action("Group", commands.group, "Ctrl+G")
        self.ungroup_action = action("Ungroup", commands.ungroup, "Ctrl+Shift+G")
        self.lock_items_action = action("Lock or Unlock", self.shortcut(commands.toggle_lock), "L")
        self.rotate_action = action(
            "Rotate 90° Clockwise", self.shortcut(lambda: commands.rotate(90)), "R"
        )
        self.rotate_back_action = action(
            "Rotate 90° Counter-clockwise", self.shortcut(lambda: commands.rotate(-90)), "Shift+R"
        )
        self.furniture_actions = [
            self.group_action,
            self.ungroup_action,
            self.lock_items_action,
            self.rotate_action,
            self.rotate_back_action,
        ]
        directions = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}
        for key, (dx, dy) in directions.items():
            for modifier, step in (("", 1), ("Shift+", 10)):
                move = self.shortcut(partial(commands.nudge, dx * step, dy * step))
                nudge = action(f"Nudge {key}", move, f"{modifier}{key}")
                self.addAction(nudge)  # shortcuts only, not in a menu
                self.furniture_actions.append(nudge)
        self.add_actions = [
            action(text, lambda _=False, t=template: commands.add(t))
            for template, text in (("rect", "Table"), ("round", "Round"), ("l_shape", "L-Shape"))
        ]
        self.obstacle_actions = [
            action(text, lambda _=False, t=template: commands.add_obstacle(t))
            for template, text in (
                ("column", "Column"),
                ("radiator", "Radiator"),
                ("cupboard", "Built-in"),
            )
        ]
        for obstacle_action in self.obstacle_actions:
            obstacle_action.setToolTip(f"Add a {obstacle_action.text().lower()} obstacle")
        self.layout_actions = [
            action("Add", self.add_layout),
            action("Rename…", self.rename_layout),
            action("Duplicate", self.duplicate_layout),
            action("Delete…", self.delete_layout),
        ]
        for layout_action, tip in zip(
            self.layout_actions,
            ("Add an empty layout", "Rename this layout", "Copy this layout", "Delete this layout"),
            strict=True,
        ):
            layout_action.setToolTip(tip)

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
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addActions([self.select_all_action, self.duplicate_action, self.delete_action])
        edit_menu.addSeparator()
        edit_menu.addActions(self.furniture_actions[:5])
        add_menu = edit_menu.addMenu("Add Furniture")
        add_menu.addActions(self.add_actions)
        apartment_menu = edit_menu.addMenu("Add to Apartment")
        apartment_menu.addActions([*self.opening_tool_actions, *self.obstacle_actions])
        edit_menu.addSeparator()
        edit_menu.addAction(self.lock_action)
        view_menu = self.menuBar().addMenu("&View")
        view_menu.addActions([self.zoom_in_action, self.zoom_out_action, self.zoom_fit_action])
        view_menu.addSeparator()
        view_menu.addAction(self.snap_action)
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

    def _create_toolbar(self) -> None:
        self.toolbar = self.addToolBar("Main")
        self.toolbar.setObjectName("main_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.addActions([self.undo_action, self.redo_action])
        self.toolbar.addSeparator()
        self.toolbar.addActions([self.lock_action, self.export_action])

    def _add_panel(self, title: str, area: Qt.DockWidgetArea, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"{title.lower()}_panel")
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setMinimumWidth(240)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock
