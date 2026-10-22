# Apartment Planner

A private 2D apartment planner desktop app for two people, written in Python
with PySide6. The full scope, data model and milestones are in
[docs/SPEC.md](docs/SPEC.md). Read the relevant section before starting a
feature, and update the spec in the same change when behaviour or scope
changes.

## Stack

Python 3.13, uv, PySide6 (`QGraphicsView`/`QGraphicsScene`), Shapely 2,
pydantic v2, pytest + hypothesis + pytest-qt, ruff, mypy (strict). Development
is on Windows, and the app must also work on macOS: use `pathlib`, no
hard-coded separators, and no OS-specific shell in tooling.

## Commands

- `uv run apartment-planner`: launch the app
- `uv run pytest`: run all tests (Qt tests run with the offscreen platform)
- `uv run mypy`: type-check
- `uv run ruff check` / `uv run ruff format`: lint / format
- `uv add <pkg>` / `uv add --dev <pkg>`: add dependencies (never pip install)

Before calling work done, run `uv run ruff check`, `uv run mypy` and
`uv run pytest`.

## Architecture

```
src/apartment_planner/
  model/        pydantic models, defaults, ids                (pure)
  geometry/     Shapely-based helpers, transforms, validation (pure)
  fit/          fit-check findings from apartment + layout     (pure)
  state/        EditorState: document, selection, history      (pure)
  persistence/  .apartment read/write, autosave, locks, migrations/  (no widgets)
  canvas/       QGraphicsScene items, view, tools, handles     (Qt)
  ui/           main window, panels, dialogs, start screen     (Qt)
tests/          mirrors the package; tests/fixtures/ holds files per schema version
```

**Layering** (enforced by `tests/test_layering.py`): `model`, `geometry`,
`fit` and `state` must not import PySide6. `persistence` may use only
`PySide6.QtCore` (for `QLockFile`), never widgets. `canvas` and `ui` read from
`EditorState` and call its actions; they never mutate the document directly.

## Invariants (don't break these)

- **The `ProjectDoc` is the source of truth.** Graphics items are views. Never
  read geometry back from items; commit computed values to the document and
  re-sync the scene.
- **World units are cm**, +y down, rotation in degrees clockwise, and scene
  units are world cm. Map view→scene only at the input boundary. Geometry,
  snapping and fit checks take world coordinates only.
- **No wall thickness.** Rooms are interior polygons; walls are their edges.
  Room vertices run clockwise on screen (the model rejects anything else).
  Never reverse a room's vertices without remapping its openings.
- **Edit models with `.evolve(**changes)`**, never `model_copy(update=...)`,
  which skips validation.
- **Openings reference `edge_start_vertex_id`, never an edge index.**
- **One user gesture = one undo entry.** Commit on mouse release or field
  Enter/focus-out, not on every move.
- **Overlap tolerance is `EPS` (0.1 cm)** via the shared helper. Touching is not
  overlapping.
- **Persisted shape changes need a schema migration.** Follow the
  `schema-change` skill.
- **Saves are atomic:** tmp file → fsync → `os.replace`. Never write directly to
  the project file, and never overwrite a file that changed on disk since it
  was loaded.
- **Never lose the last good save.** Save errors are surfaced and retried,
  never swallowed.
- No network access at runtime.

## Testing

- **Every test must fail under some plausible mutation of the code.** No
  padding: don't test library behaviour (pydantic, Shapely, Qt), don't repeat
  a case another test already covers, and don't add property tests that only
  restate an example test. Prefer boundary cases (just below and just above a
  threshold such as `EPS` or `MIN_EDGE_LENGTH`).
- Mutation testing (cosmic-ray) is optional and only run when asked: a full
  run takes about half an hour. `uv run python mutation/run.py` tests the
  committed HEAD in a throwaway worktree and writes surviving mutants to
  `mutation/last-report.txt`. When it is run, kill survivors with tests; a
  truly equivalent mutant gets `# pragma: no mutate` with a comment saying why.
- Add new pure packages to `module-path` in `mutation/pure.toml`.

## Conventions

- Prefer small pure functions with tests over logic in Qt classes.
- Geometry and persistence code is written test-first, or at least with its
  tests in the same change.
- Full type hints everywhere; `mypy --strict` must pass. Use `from __future__
  import annotations` only where needed for forward references.
- IDs come from `model.ids.new_id()`.
- Name things in domain terms (room, opening, layout, furniture, obstacle) as
  the spec uses them; snake_case in code and JSON.
- User-facing messages say what happened and how to fix it, plainly, without
  apologising.
