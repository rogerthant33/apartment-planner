import math
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage
from pytestqt.qtbot import QtBot

from apartment_planner.canvas.tools import Pointer
from apartment_planner.model import new_project
from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.files import create_project_file, read_project
from apartment_planner.state.editor import EditorState
from apartment_planner.state.rooms import add_room
from apartment_planner.ui import dialogs
from apartment_planner.ui.main_window import MainWindow
from tests.factories import NOW


def png(folder: Path, width: int, height: int) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    path = folder / "made.png"
    image.save(str(path))
    return path.read_bytes()


@pytest.fixture
def window(qtbot: QtBot, settings: QSettings, folder: Path) -> Iterator[MainWindow]:
    doc, _ = add_room(new_project("Flat", now=NOW), [(0, 0), (400, 0), (400, 300), (0, 300)])
    path = folder / "Flat.apartment"
    create_project_file(path, ProjectFile(doc))
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.show()
    window.open_path(path)
    yield window
    window.close_project()


def editor(window: MainWindow) -> EditorState:
    assert window.editor is not None
    return window.editor


def import_image(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, data: bytes
) -> None:
    image = tmp_path / "plan.png"
    image.write_bytes(data)
    monkeypatch.setattr(dialogs, "open_image", lambda *args: image)
    window.import_background_action.trigger()


def click(window: MainWindow, x: float, y: float) -> None:
    window.view.tool.press(Pointer((x, y), cm_per_px=1.0, snapping=False))


def test_imported_image_is_calibrated_by_two_clicks_and_saved(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = png(tmp_path, 200, 100)
    import_image(window, monkeypatch, tmp_path, data)
    assert window.view.tool is window.view.tools["calibrate"]
    assert window.view.plan.background is not None

    monkeypatch.setattr(dialogs, "ask_text", lambda *args: "5 m")
    click(window, 10, 10)
    click(window, 110, 10)  # 100 px apart at 1 cm per px

    bg = editor(window).doc.background
    assert bg is not None
    assert bg.cm_per_pixel == pytest.approx(5)
    assert window.view.tool is window.view.tools["select"]
    assert window.project is not None and window.project.flush()
    saved = read_project(window.project.path)
    assert saved.project.assets == {bg.asset_id: data}


def test_files_that_are_not_images_are_refused(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    errors: list[str] = []
    monkeypatch.setattr(dialogs, "show_error", lambda parent, title, text: errors.append(text))

    import_image(window, monkeypatch, tmp_path, b"\x89PNG\r\n\x1a\nnot really")

    assert editor(window).doc.background is None
    assert errors == [
        "plan.png isn't a PNG, JPEG or WebP image this app can read. "
        "Export the plan as one of those and import it again."
    ]


def test_image_moves_by_dragging_until_locked(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import_image(window, monkeypatch, tmp_path, png(tmp_path, 200, 100))
    before = editor(window).doc.background
    assert before is not None
    window.set_tool("image")

    def drag(dx: float) -> None:
        tool = window.view.tool
        tool.press(Pointer((0, 0), cm_per_px=1.0, snapping=False))
        tool.move(Pointer((dx, 0), cm_per_px=1.0, snapping=False))
        tool.release(Pointer((dx, 0), cm_per_px=1.0, snapping=False))

    drag(30)
    box = window.properties.settings_page.background
    box.locked.setChecked(True)
    drag(30)

    after = editor(window).doc.background
    assert after is not None
    assert (after.origin.x - before.origin.x, after.locked) == (30, True)
    assert math.isclose(after.origin.y, before.origin.y)
