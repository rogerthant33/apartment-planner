import sys
from pathlib import Path

from PySide6.QtCore import QDir, QProcess, QUrl
from PySide6.QtGui import QDesktopServices


def show_in_folder(path: Path) -> None:
    """Open the file manager with `path` selected where the platform supports it."""
    if sys.platform == "win32":
        QProcess.startDetached("explorer.exe", ["/select,", QDir.toNativeSeparators(str(path))])
    elif sys.platform == "darwin":
        QProcess.startDetached("open", ["-R", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
