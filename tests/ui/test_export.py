from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QImage
from pytestqt.qtbot import QtBot

from apartment_planner.model import ProjectDoc, new_project
from apartment_planner.persistence.archive import ProjectFile
from apartment_planner.persistence.files import create_project_file
from apartment_planner.state.rooms import add_room
from apartment_planner.ui import dialogs
from apartment_planner.ui.export import ExportError, PdfOptions, export_pdf, export_png
from apartment_planner.ui.export_dialog import ExportChoice, ExportDialog
from apartment_planner.ui.main_window import MainWindow
from tests.factories import NOW


def flat(width: float = 400) -> ProjectDoc:
    doc, _ = add_room(new_project("Flat", now=NOW), [(0, 0), (width, 0), (width, 300), (0, 300)])
    return doc


def test_png_covers_the_plan_and_its_margin_at_the_chosen_resolution(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "plan.png"

    export_png(flat(), path, px_per_m=100)

    image = QImage(str(path))
    assert image.width() == 500  # 400 cm plus 50 cm each side, at 1 px per cm
    assert image.height() == 400 + 2 * 42  # plus the title and scale-bar bands


@pytest.mark.parametrize(
    ("width", "options", "expected"),
    [
        (400, PdfOptions(scale=50), 50),
        (1300, PdfOptions(scale=50), None),  # 1400 cm is 280 mm at 1:50, wider than A4
        (1300, PdfOptions(scale=100), 100),
        (1300, PdfOptions(paper="A3", scale=50), 50),
        (400, PdfOptions(scale=None), None),
    ],
)
def test_pdf_is_to_scale_when_it_fits(
    qtbot: QtBot, tmp_path: Path, width: float, options: PdfOptions, expected: int | None
) -> None:
    path = tmp_path / "plan.pdf"

    assert export_pdf(flat(width), path, options) == expected
    assert path.read_bytes().startswith(b"%PDF")


def test_an_empty_plan_is_not_exported(qtbot: QtBot, tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="nothing to export yet"):
        export_png(new_project("Flat", now=NOW), tmp_path / "plan.png")


@pytest.fixture
def window(qtbot: QtBot, settings: QSettings, folder: Path) -> Iterator[MainWindow]:
    path = folder / "Flat.apartment"
    create_project_file(path, ProjectFile(flat(1300)))
    window = MainWindow(settings)
    qtbot.addWidget(window)
    window.show()
    window.open_path(path)
    yield window
    window.close_project()


def test_export_says_when_the_plan_was_fitted_to_the_page(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chosen: list[Path] = []

    def save_export(parent: object, suggested: Path, format: str) -> Path:
        chosen.append(suggested)
        return tmp_path / "out.pdf"

    monkeypatch.setattr(dialogs, "ask_export", lambda parent: ExportChoice(format="pdf"))
    monkeypatch.setattr(dialogs, "save_export", save_export)

    window.export_action.trigger()

    assert [p.name for p in chosen] == ["Flat - Layout 1.pdf"]
    assert (tmp_path / "out.pdf").exists()
    assert window.statusBar().currentMessage() == (
        "Exported out.pdf. The plan doesn't fit on A4 at 1:50, so it was fitted to the page; "
        "try A3 or 1:100 to print it to scale."
    )


def test_export_dialog_reads_its_choices(qtbot: QtBot) -> None:
    dialog = ExportDialog()
    qtbot.addWidget(dialog)

    dialog.paper.setCurrentText("A3")
    dialog.orientation.setCurrentText("Portrait")
    dialog.scale.setCurrentIndex(2)  # fit to page
    assert dialog.choice().pdf == PdfOptions(paper="A3", landscape=False, scale=None)
    dialog.format.setCurrentIndex(1)
    dialog.resolution.setValue(300)
    dialog.warnings.setChecked(True)

    choice = dialog.choice()
    assert (choice.format, choice.px_per_m, choice.warnings) == ("png", 300, True)
    assert dialog.paper.isHidden()


def test_an_image_too_big_to_make_asks_for_a_lower_resolution(qtbot: QtBot, tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="Choose a lower resolution"):
        export_png(flat(400_000), tmp_path / "plan.png", px_per_m=1000)
