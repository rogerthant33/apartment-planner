"""The start screen: the project library, shown when no project is open."""

from collections.abc import Iterator
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from apartment_planner.persistence.errors import ProjectFileError
from apartment_planner.persistence.library import (
    Library,
    delete_project,
    duplicate_project,
    project_name,
    rename_project,
)
from apartment_planner.ui import dialogs
from apartment_planner.ui.reveal import show_in_folder

PATH_ROLE = Qt.ItemDataRole.UserRole


COLUMN_WIDTH = 820  # px


class StartScreen(QWidget):
    open_requested = Signal(Path)
    new_requested = Signal()
    browse_requested = Signal()

    def __init__(self, library: Library, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library

        self.folder_label = QLabel()
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        change_folder = QPushButton("Change…")
        change_folder.clicked.connect(self.change_folder)

        self.projects = QTreeWidget()
        self.projects.setHeaderLabels(["Name", "Last modified"])
        self.projects.setRootIsDecorated(False)
        header = self.projects.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.empty_hint = QLabel(
            "No projects here yet. Choose New… to start one, or Open… to find one elsewhere."
        )
        self.projects.itemActivated.connect(lambda item: self.open_requested.emit(_path(item)))
        self.projects.itemSelectionChanged.connect(self._update_buttons)

        self.buttons: dict[str, QPushButton] = {}
        actions = {
            "New…": self.new_requested.emit,
            "Open…": self.browse_requested.emit,
            "Rename…": self.rename_selected,
            "Duplicate": self.duplicate_selected,
            "Delete…": self.delete_selected,
            "Show in Folder": self.show_selected,
        }
        button_row = QHBoxLayout()
        for text, slot in actions.items():
            button = QPushButton(text)
            button.clicked.connect(slot)
            button_row.addWidget(button)
            self.buttons[text] = button
        button_row.addStretch()

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Projects folder:"))
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(change_folder)

        # A column of readable width, centred in the window.
        column = QWidget()
        column.setMaximumWidth(COLUMN_WIDTH)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 24, 0, 24)
        layout.setSpacing(10)
        title = QLabel("Apartment Planner")
        title.setStyleSheet("font-size: 20pt; font-weight: 600;")
        layout.addWidget(title)
        layout.addLayout(folder_row)
        layout.addWidget(self.empty_hint)
        layout.addWidget(self.projects, 1)
        layout.addLayout(button_row)
        outer = QHBoxLayout(self)
        outer.addStretch()
        outer.addWidget(column, 100)
        outer.addStretch()

        self.refresh()

    def refresh(self) -> None:
        self.folder_label.setText(str(self.library.folder))
        self.projects.clear()
        for entry in self.library.entries():
            item = QTreeWidgetItem([entry.name, entry.modified.strftime("%Y-%m-%d %H:%M")])
            item.setData(0, PATH_ROLE, str(entry.path))
            item.setToolTip(0, str(entry.path))
            self.projects.addTopLevelItem(item)
        self.empty_hint.setVisible(self.projects.topLevelItemCount() == 0)
        for item in self._items():
            self.projects.setCurrentItem(item)
            break
        self._update_buttons()

    def selected_path(self) -> Path | None:
        item = self.projects.currentItem()
        return _path(item) if item is not None and item.isSelected() else None

    def select(self, path: Path) -> None:
        for item in self._items():
            if _path(item) == path:
                self.projects.setCurrentItem(item)

    def _items(self) -> Iterator[QTreeWidgetItem]:
        for i in range(self.projects.topLevelItemCount()):
            item = self.projects.topLevelItem(i)
            if item is not None:
                yield item

    def change_folder(self) -> None:
        folder = dialogs.choose_folder(self, self.library.folder)
        if folder is not None:
            self.library.folder = folder
            self.refresh()

    def rename_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        name = dialogs.ask_project_name(self, "Rename Project", project_name(path))
        if name is None:
            return
        try:
            target = rename_project(path, name)
        except (ProjectFileError, OSError) as error:
            dialogs.show_error(self, "Couldn't Rename Project", dialogs.error_message(error))
            return
        self.library.replace_recent(path, target)
        self.refresh()
        self.select(target)

    def duplicate_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        try:
            copy = duplicate_project(path)
        except (ProjectFileError, OSError) as error:
            dialogs.show_error(self, "Couldn't Duplicate Project", dialogs.error_message(error))
            return
        if copy.parent != self.library.folder:
            self.library.add_recent(copy)
        self.refresh()
        self.select(copy)

    def delete_selected(self) -> None:
        path = self.selected_path()
        if path is None:
            return
        question = f'Move "{project_name(path)}" to the trash?'
        if not dialogs.confirm(self, "Delete Project", question, "Move to Trash"):
            return
        try:
            delete_project(path)
        except (ProjectFileError, OSError) as error:
            dialogs.show_error(self, "Couldn't Delete Project", dialogs.error_message(error))
            return
        self.library.remove_recent(path)
        self.refresh()

    def show_selected(self) -> None:
        path = self.selected_path()
        if path is not None:
            show_in_folder(path)

    def _update_buttons(self) -> None:
        has_selection = self.selected_path() is not None
        for text in ("Rename…", "Duplicate", "Delete…", "Show in Folder"):
            self.buttons[text].setEnabled(has_selection)


def _path(item: QTreeWidgetItem) -> Path:
    return Path(item.data(0, PATH_ROLE))
