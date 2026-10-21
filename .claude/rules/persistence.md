---
paths:
  - "src/apartment_planner/persistence/**"
  - "src/apartment_planner/model/**"
  - "tests/persistence/**"
  - "tests/fixtures/**"
---

# Persistence and schema rules

- Any change to a persisted model (`ProjectDoc` and everything inside it, or
  the archive layout) is a schema change. Follow the `schema-change` skill.
- Never edit or delete existing files in `tests/fixtures/`. They record what
  old files look like. Add new ones instead.
- All writes to a `.apartment` file go through the save function in
  `persistence/`: write `<file>.tmp`, flush and `os.fsync`, then `os.replace`.
  Nothing else opens a project file for writing.
- Before replacing, compare the on-disk fingerprint (size, mtime, SHA-256)
  with the one recorded at load or last save. If it differs, write a conflict
  copy instead.
- Loading never modifies the file, even when migrations run. The migrated
  version is written by the next normal save.
- `persistence` may import `PySide6.QtCore` only. No dialogs: anything that
  needs user confirmation takes the decision as an argument.
- Raise typed errors (subclasses of `ProjectFileError`) with user-readable
  messages. Never swallow exceptions with a bare `except` or `except
  Exception: pass`.
- Tests use pytest's `tmp_path`. Simulate failures (read-only file, replace
  raising `PermissionError`, file changed underneath) with monkeypatch rather
  than real OS tricks, so tests run the same on Windows and macOS.
