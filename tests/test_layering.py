"""Enforce the package layering described in CLAUDE.md."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parent.parent / "src" / "apartment_planner"

PURE = ["model", "geometry", "fit", "state"]


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def files_in(subpackage: str) -> list[Path]:
    return sorted((PACKAGE / subpackage).rglob("*.py"))


@pytest.mark.parametrize("subpackage", PURE)
def test_pure_packages_do_not_import_qt_or_ui(subpackage: str) -> None:
    for path in files_in(subpackage):
        for module in imported_modules(path):
            assert not module.startswith(("PySide6", "shiboken6")), f"{path} imports {module}"
            assert not module.startswith(
                tuple(f"apartment_planner.{p}" for p in ("canvas", "ui", "persistence"))
            ), f"{path} imports {module}"


def test_persistence_uses_only_qtcore() -> None:
    for path in files_in("persistence"):
        for module in imported_modules(path):
            if module.startswith("PySide6"):
                assert module == "PySide6.QtCore", f"{path} imports {module}"
            assert not module.startswith(("apartment_planner.canvas", "apartment_planner.ui")), (
                f"{path} imports {module}"
            )


def test_layering_test_sees_the_package() -> None:
    assert files_in("model"), "layering test is looking in the wrong place"
