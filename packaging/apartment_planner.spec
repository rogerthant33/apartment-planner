# PyInstaller build for Windows, macOS and Linux. Run `uv run python packaging/build.py`.
# A one-folder build starts faster than a one-file one; on macOS it becomes an .app.
import sys

NAME = "Apartment Planner"

analysis = Analysis(  # noqa: F821 (PyInstaller provides these names)
    ["launch.py"],
    pathex=["../src"],
    # Only QtCore, QtGui and QtWidgets are used; leave out the rest of Qt.
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    exclude_binaries=True,
    name=NAME,
    console=False,  # a windowed app: no terminal on Windows
    upx=False,
)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, name=NAME, upx=False)  # noqa: F821
if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        bundle,
        name=f"{NAME}.app",
        bundle_identifier="local.apartment-planner",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleDocumentTypes": [
                {"CFBundleTypeName": "Apartment project", "CFBundleTypeExtensions": ["apartment"]}
            ],
        },
    )
