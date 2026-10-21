from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from apartment_planner.persistence.library import Library


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    """Settings in a temporary file, with the projects folder inside tmp_path."""
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    Library(settings).folder = tmp_path / "Projects"
    return settings


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    folder = tmp_path / "Projects"
    folder.mkdir()
    return folder
