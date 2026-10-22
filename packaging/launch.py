"""Entry point for the packaged app (PyInstaller needs a script, not a module)."""

from apartment_planner.__main__ import main

raise SystemExit(main())
