"""Build the packaged app for this platform into dist/. Works the same on Windows,
macOS and Linux: `uv run python packaging/build.py`."""

from pathlib import Path

import PyInstaller.__main__

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main() -> None:
    PyInstaller.__main__.run(
        [
            str(HERE / "apartment_planner.spec"),
            "--noconfirm",
            "--clean",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build"),
        ]
    )


if __name__ == "__main__":
    main()
