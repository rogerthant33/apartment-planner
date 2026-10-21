"""Enforce the package layering described in CLAUDE.md.

Relative imports are banned by ruff (TID252), so absolute module names are
enough here.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parent.parent / "src" / "apartment_planner"

QT = ("PySide6", "shiboken6")
UI_LAYERS = ("apartment_planner.canvas", "apartment_planner.ui")
PURE_FORBIDDEN = (*QT, *UI_LAYERS, "apartment_planner.persistence")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def imports_in(subpackage: str) -> list[tuple[Path, str]]:
    directory = PACKAGE / subpackage
    if not directory.is_dir():
        pytest.skip(f"{subpackage}/ doesn't exist yet")
    return [(path, m) for path in sorted(directory.rglob("*.py")) for m in imported_modules(path)]


@pytest.mark.parametrize("subpackage", ["model", "geometry", "fit", "state"])
def test_pure_packages_do_not_import_qt_or_io(subpackage: str) -> None:
    for path, module in imports_in(subpackage):
        assert not module.startswith(PURE_FORBIDDEN), f"{path} imports {module}"


def test_persistence_uses_only_qtcore() -> None:
    for path, module in imports_in("persistence"):
        if module.startswith(QT):
            assert module == "PySide6.QtCore", f"{path} imports {module}"
        assert not module.startswith(UI_LAYERS), f"{path} imports {module}"
