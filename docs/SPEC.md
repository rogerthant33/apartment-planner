# Apartment Planner — MVP Specification (v3)

This is the source of truth for scope. It revises the original brief. When the
code and this document disagree, fix one of them; don't let them drift.

## 1. Overview

A private 2D apartment planner for two people, built as a cross-platform
Python desktop app (Windows first; macOS must also work). You draw the
apartment's rooms using interior measurements, add doors, windows and fixed
obstacles, then try out several furniture layouts and check what fits.

**Principles**

- Accurate real-world dimensions; the screen is only a view.
- Simple, direct editing with immediate visual feedback.
- Never lose work: automatic saving to the project file, visible save status,
  atomic writes.
- Fully local: no backend, accounts, AI or network access.

**Changes from the original brief**

- **Desktop app in Python** (PySide6) instead of a browser app. A project is a
  single `.apartment` file on disk, which replaces IndexedDB and the separate
  export/import format. Sharing means sending the file or keeping it in a
  shared cloud folder.
- **No wall thickness.** Rooms are interior floor polygons, which is what you
  measure with a tape. Walls are the polygon edges.
- **Multiple furniture layouts per apartment.** The apartment geometry is
  shared; each layout has its own furniture.
- **Additions:** door swing arcs count in fit checks, keyboard shortcuts, plan
  export to PNG and PDF, lock files and conflict detection for shared folders.

## 2. Technology

| Concern | Choice |
| --- | --- |
| Language | Python 3.13 |
| Project / env | uv (`pyproject.toml`, `uv.lock`) |
| UI / canvas | PySide6 (Qt 6): `QGraphicsView` / `QGraphicsScene` |
| Geometry | Shapely 2 |
| Data model / validation | pydantic v2 |
| Tests | pytest, hypothesis (geometry properties), pytest-qt (UI) |
| Lint / format / types | ruff, mypy (strict, pydantic plugin) |
| Packaging | PyInstaller, one-folder build per OS (`packaging/build.py`); macOS gets an `.app` |

## 3. Interface

Desktop-first main window with three columns.

- **Left panel:** layout switcher (add, rename, duplicate and delete layouts),
  tools, "add to the apartment" tools and obstacle templates (enabled while
  the apartment is unlocked), "add furniture" templates (table, round table,
  L-shaped corner sofa, placed at the centre of the view), the room list and
  the furniture list.
  Unticking an item in the furniture list hides it from the canvas for this
  session only; hidden items can't be selected.
- **Canvas:** grid, rooms, openings, obstacles, furniture, dimension labels and
  warnings. Zoom, pan, selection, drag, resize and rotate.
- **Right panel:** properties of the selection (numeric dimensions, position,
  rotation, label, color, notes, metadata), actions (duplicate, delete, lock,
  group), and the warnings list for the current layout.
- **Toolbar:** undo/redo, "Apartment locked" toggle, export plan. The **status
  bar** shows save status: Saving… (while a save is waiting or running) /
  Saved / Save failed — retrying / Read-only.
- **Menus:** File (New, Open…, Open Recent, Save Now, Save a Copy As…,
  Rename…, Show in Folder, Export Plan…, Close, Quit), Edit, View, Help.

### Start screen

Shown when no project is open. It lists `.apartment` files in the projects
folder (default `Documents/Apartment Planner/`, configurable) plus recent files
from elsewhere, with name and last-modified time, newest first. A project's
name is its file name. Actions: New, Open…, Rename, Duplicate (a new project
named "<name> copy"), Delete (moves the file and its `.bak` to the OS trash
after confirmation), Show in Folder, and changing the projects folder.

## 4. Coordinates and units

- World units are **centimetres**, stored as floats. +x right, +y down. Rotation
  is in **degrees, clockwise**, about the object's origin. This matches Qt
  scene coordinates exactly.
- **Scene units are world cm.** Zoom and pan are only the `QGraphicsView`
  transform and never change the document.
- All geometry, snapping and fit checks run in world coordinates. View
  coordinates are mapped to scene coordinates at the input boundary
  (`mapToScene`) and nowhere else.
- Display unit: mm / cm / m. It only affects formatting and parsing of input.
- Grid size is configurable (default 10 cm). Snapping can be toggled; hold Alt
  to suspend it during a drag.
- Dimension labels keep a constant screen size
  (`ItemIgnoresTransformations`).

## 5. Apartment editor

### Rooms

- Draw rectangular rooms (drag) or polygon rooms (click points, close on the
  first point or with Enter; Backspace removes the last point, Escape
  cancels). New rooms are named "Room 1", "Room 2", … and selected.
- Edit vertices by dragging; edit edge lengths numerically in the properties
  panel (edges are numbered from the first vertex; the edge's end vertex
  moves along the edge direction).
- Insert a vertex on an edge (double-click); delete a vertex (select + Delete,
  minimum 3).
- Add, rename, duplicate and delete rooms. Each room has a name label at its
  centroid (or inside it, for shapes whose centroid falls outside) and shows
  its area. The selected room shows its edge lengths. A duplicate is named
  "<name> copy", copies the room's openings and is offset by 50 cm. Deleting
  a room deletes its openings and unassigns furniture placed in it.
- Adjacent rooms share boundaries by snapping vertices and edges together.
  There is no wall graph: each room owns its polygon.
- Vertex snapping: to other rooms' vertices, then to their edges (both within
  10 px on screen), then to the grid.

### Validation

A room or polygon is valid when it has ≥ 3 vertices, no edge shorter than 1 cm,
and is a valid simple polygon (Shapely `is_valid`, positive area). Invalid
edits show a red preview while dragging and **revert on release** with a
message saying why. Numeric input that would produce invalid geometry is
rejected inline. Overlapping rooms are allowed but produce a warning.

### Doors and windows (openings)

- Placed on a room edge, referenced by `room_id` + `edge_start_vertex_id` +
  `offset` (cm from the edge start to the opening's centre) + `width`.
- Because they reference a vertex ID, not an edge index, they stay attached
  when other vertices are added or removed. When an edge's length changes, the
  offset is clamped so the opening stays on the edge. If the referenced vertex
  is deleted, the opening moves to the merged edge, keeping its world position
  as closely as possible.
- **Doors:** hinge side (`start`/`end`), swing (`in` = into the owning room,
  `out` = away from it), shown as a quarter-circle swing arc. The swing area
  is part of fit checking.
- **Windows:** drawn as a thin double line across the edge.
- Plain openings (no door) are supported for archways.
- The Door, Window and Opening tools (D, W, O) place one where you click,
  on the nearest wall within 25 px, at a grid step along it, with a default
  width (door 80 cm, window 120 cm, opening 90 cm; at most the wall's
  length). A new door hinges at the wall's start and swings in.
- Drag an opening along its wall or onto another wall (of any room) to move
  it. The properties panel edits its kind, width (at most the wall's
  length), offset, and a door's hinge and swing. Changing a door to another
  kind drops its hinge and swing.

### Fixed obstacles

Columns, built-in cupboards, radiators and so on. Same shape model as
furniture, but they belong to the apartment (shared across layouts) and are
edited only while the apartment is unlocked. They are drawn hatched, and are
added from templates (Column 30 × 30, Radiator 100 × 10, Built-in cupboard
120 × 60 cm) at the centre of the view. They move, resize, rotate, nudge,
duplicate and delete like furniture, but have no category, clearance,
product details, lock or group. A selection holds either furniture or
obstacles: Shift+clicking the other kind starts a new selection.

### Apartment lock

When locked, rooms, openings and obstacles can't be selected or moved, so
furniture arranging can't disturb them. A project that has rooms always opens
locked; that alone doesn't count as a change to save.

## 6. Furniture

### Shapes

- `rect` (width × depth), `ellipse` (rx, ry; circle when equal), `polygon`
  (local-coordinate points). L-shapes are polygons; include an "L-shape"
  template that generates one from four dimensions.
- The model keeps a discriminated `type` so curved segments can be added later
  as a new shape type without migrating old data.

### Properties

`id`, `name`, `category?`, `shape`, `x`, `y` (world position of the local
origin), `rotation`, `color?`, `notes?`, `room_id?`, `locked`, `group_id?`,
`clearance?` (cm, overrides the project default), `meta?` (`product`, `url`,
`price`).

`room_id` is kept up to date automatically: it names the room the item's
origin stands in. New items get numbered names ("Table", "Table 2", …). The
properties panel edits every field of a single item (width and depth for
rectangles and ellipses, edge lengths for polygons); several selected items
get group, ungroup, lock, unlock, duplicate and delete.

### Manipulation

- Select (click, Shift+click, rubber band touching the items), drag, move
  multiple selected items. Furniture can be selected whether or not the
  apartment is locked.
- Resize with handles or numeric input; rotate with a handle (snaps to 15°
  increments, hold Alt for free rotation) or numeric input. A single item
  turns about its origin; several turn about the centre of their footprints.
- Duplicate (copies are unlocked and offset by 50 cm; copies of a group form a
  new group), delete, rename, group/ungroup (groups select and move together;
  a group with fewer than two members dissolves), lock (a locked item can't be
  moved, resized, rotated or deleted, but can be renamed and unlocked).
- Snap to room edges (flush against a wall) and to other items' edges when a
  corner comes within 10 px of one; otherwise the item's origin snaps to the
  grid. Alt suspends snapping.

### Custom polygon drawing

The polygon tool (P) draws a room while the apartment is unlocked and a
custom furniture shape while it is locked. Click points; close on the first
point or with Enter; Escape cancels. Show edge lengths while drawing and
after creation. Edit vertices by dragging or numerically. Validated like
rooms (either winding is fine). The shape's origin is the centre of its
bounding box.

### Keyboard shortcuts

Ctrl means Cmd on macOS. Use `QKeySequence.StandardKey` where one exists.

| Key | Action |
| --- | --- |
| Arrow keys | Nudge 1 cm (Shift: 10 cm) |
| R / Shift+R | Rotate +90° / −90° |
| Ctrl+D | Duplicate |
| Delete / Backspace | Delete selection |
| Ctrl+Z / Ctrl+Shift+Z (Ctrl+Y) | Undo / redo |
| Ctrl+A | Select all furniture in the layout |
| Ctrl+G / Ctrl+Shift+G | Group / ungroup |
| L | Lock / unlock selection |
| Escape | Cancel the current tool / clear the selection |
| Space + drag, middle-drag | Pan |
| Ctrl + wheel, pinch | Zoom at the cursor |
| 0 | Zoom to fit |
| V, M, P | Select tool, rectangle room tool, polygon tool |
| D, W, O | Door, window and opening tools |
| Ctrl+S | Save now (flush autosave) |
| Ctrl+N / Ctrl+O | New / Open |
| Ctrl+E | Export plan |

Shortcuts are ignored while a text field has focus.

## 7. Fit checking

Pure functions in `fit/` that take the apartment plus a layout and return a
list of `Finding`s. Recomputed after every committed change (cached by document
revision).

**Tolerance.** An overlap counts only if the intersection region contains a
disk of diameter `EPS = 0.1` cm, implemented as
`not intersection.buffer(-EPS / 2).is_empty`. Touching, or slivers thinner than
1 mm, are not collisions, so furniture flush against a wall or another item
doesn't trigger a warning.

**Curves.** Ellipses are converted to 48-segment polygons by one shared helper.
Rendering uses the true ellipse.

| Check | Severity |
| --- | --- |
| Furniture overlaps furniture | collision |
| Furniture overlaps an obstacle | collision |
| Furniture not contained in the union of rooms (crosses a wall or sits outside) | collision |
| Furniture intersects a door's swing area | collision |
| Furniture blocks a doorway or opening (within `default_clearance` depth on either side) | warning |
| Item's clearance zone intersects another item, obstacle or wall | warning |
| Rooms overlap each other | warning |
| A room or polygon shape is invalid (it is then left out of the other checks) | warning |

- Clearance zones are opt-in: only items with `clearance` set have one, so
  furniture flush against a wall isn't flagged by default. Clearance violation
  means `distance(a, b) < clearance - EPS`; items that already overlap aren't
  reported again, and each pair is reported once. Every room edge counts as a
  wall, including edges shared by two rooms. The zone is drawn as
  `polygon.buffer(clearance)`, translucent, behind the item.
- `settings.default_clearance` is the depth kept free in front of doors and
  plain openings (not windows), on both sides of the wall. An item in a
  door's swing is a collision and isn't also reported as blocking that door.
- Collisions are red, warnings amber. Affected items (furniture, obstacles,
  rooms) are outlined. The Fit Checks panel, below the properties, counts and
  explains the findings, collisions first. Clicking one selects its furniture,
  or its obstacles or rooms while the apartment is unlocked.
- Selecting two items shows the minimum distance between them. Selecting one
  item shows, for each of its rotated sides (left, right, back, front), how
  far it could slide that way before reaching a wall. Flush sides show no
  readout.
- Nothing is ever blocked. Findings are informational.

## 8. Project files and saving

### File format: `<name>.apartment`

A ZIP archive:

```
project.json         # { "format": "apartment-planner", "schema_version": 1, "project": {...} }
assets/<asset_id>.<ext>   # background images, stored uncompressed (ZIP_STORED)
```

- `project.json` is deflate-compressed, UTF-8 and pretty-printed (2-space
  indent, stable key order), so it's readable after unzipping and diffs
  cleanly.
- It contains everything needed to rebuild the project and nothing derived:
  no viewport, selection, undo history or findings.

### Autosave

- Edits update the in-memory document immediately. A save is scheduled
  **750 ms** after the last committed change.
- Save procedure: write the full archive to `<name>.apartment.tmp` in the same
  folder → flush and `fsync` → `os.replace` onto the real file. The previous
  file stays intact until the replace succeeds.
- The first save in each session first copies the existing file to
  `<name>.apartment.bak` (one generation), so a bad session can be undone
  outside the app.
- Only one save runs at a time. Changes made during a save trigger another
  save when it finishes.
- On failure (disk full, permissions, a file held by antivirus or a sync
  client): the status shows "Save failed — retrying" with the reason on hover,
  then retries after 1 s, 2 s and 5 s, then every 10 s. The in-memory document
  is kept.
- Saves flush immediately on Ctrl+S, on switching projects, and on quit.
  Quitting while a save is failing asks: retry, save a copy elsewhere, or quit
  without saving.

### Sharing between two people

Projects may live in a shared cloud folder (Dropbox, OneDrive, iCloud).

- **Lock file:** opening a project creates `<name>.apartment.lock` (Qt
  `QLockFile`, holding the computer's host name and the PID). A lock left by a
  crashed app on the same computer is cleared automatically; locks never
  expire with age, because a project can stay open for days. If someone else
  holds the lock, the project opens **read-only** with a banner naming the
  computer that has it open, plus an option to save an editable copy. If the
  lock file can't be created (a read-only folder), the project also opens
  read-only.
- **External-change detection:** remember the file's size, mtime and SHA-256
  after each load or save. Before each save, if the file on disk has changed,
  don't overwrite it. Save to `<name> (conflict <date>).apartment` instead,
  continue working in that copy (it takes over the lock), and show a banner
  explaining what happened. A file deleted on disk counts as changed.

### Project management

New (choose a name; created in the projects folder), Open, Open Recent, Rename
(renames the file and its `.bak`, refused while someone else has it open; the
open project's stored name follows), Save a Copy As (new project ID; never
replaces an existing file), Delete (to OS trash, with confirmation), Show in
Folder. Names must work as file names on Windows and macOS. Recent files (up
to 10), the projects folder and window geometry are stored in `QSettings`.

### Loading

1. Open the ZIP and read `project.json`. Check that `format` matches.
2. If `schema_version` is newer than the app's, refuse with "This file was
   made by a newer version of Apartment Planner".
3. Run migrations one version at a time up to the current version, then
   validate with the pydantic model.
4. Check that every referenced asset exists in the archive.
5. Errors name the problem and the failing field path. A file that fails to
   load is never modified.

## 9. Plan export

- **PNG:** render the active layout (rooms, labels, dimensions, openings,
  furniture, a scale bar and a title) with `QGraphicsScene.render` into a
  `QImage` at roughly 150 px per metre of plan (configurable), fitted to the
  content bounds. Warnings are optional and off by default.
- **PDF:** the same rendering through `QPdfWriter`, A4 or A3, portrait or
  landscape, printed **to a stated scale** (1:50 or 1:100) when it fits,
  otherwise fit-to-page with the scale bar shown.
- File → Export Plan… (Ctrl+E) asks for the format and its options, then
  where to save (suggesting "<project> - <layout>" next to the project). The
  drawing shows every room's edge lengths, 50 cm of space around the plan, a
  title (with the scale when printed to scale) and a round-length scale bar;
  no grid, selection or background image. To-scale PDFs are centred on the
  page. If the plan doesn't fit at the chosen scale, the status bar says it
  was fitted to the page instead.

## 10. Background floor-plan image

- Import a PNG, JPG or WebP image; it's stored as an asset in the project
  file.
- **Two-point calibration:** click two points on the image and enter the real
  distance between them. Then position (drag) and optionally rotate the image.
- Opacity, visibility and lock controls. Rooms can be traced over it.
- The calibration is saved in the project.
- Import (File menu, or the "Background image" box under the project
  settings) replaces any earlier image. It arrives unlocked at 1 cm per pixel,
  centred in the view, and the Calibrate tool starts: click two points, then
  enter the distance (such as 3.5 m). Calibration scales the image about the
  first point. The Move tool drags it while it's unlocked; rotation turns it
  about its top-left corner. Image edits are undoable like any other change.
- Only PNG, JPEG and WebP files are taken, recognised by their contents. The
  image is drawn under the rooms, included in zoom to fit, and left out of
  plan exports.

## 11. Data model (schema v1)

pydantic v2 models with `extra="forbid"`, `allow_inf_nan=False` and
`frozen=True`. Sequences are tuples in code (lists in JSON), so documents are
immutable and undo snapshots can share them. JSON field names are snake_case.
Edits use `Model.evolve(**changes)`, which re-runs validation
(`model_copy(update=...)` doesn't).

The authoritative definition is `src/apartment_planner/model/project.py`. This
sketch summarises it and must be kept in step.

```text
ID = str          # uuid4 hex string, from model/ids.py

class Point:      x: float; y: float
class Vertex(Point): id: ID

class ProjectDoc:
    id: ID
    name: str
    created_at: datetime            # timezone-aware UTC
    updated_at: datetime
    settings: ProjectSettings
    apartment: Apartment
    layouts: list[Layout]           # at least one
    active_layout_id: ID
    background: BackgroundImage | None = None

class ProjectSettings:
    display_unit: Literal["mm", "cm", "m"] = "cm"
    grid_size: float = 10           # cm, > 0
    snap_enabled: bool = True
    default_clearance: float = 60   # cm, >= 0: depth kept free in front of doorways
    apartment_locked: bool = False

class Apartment:
    rooms: list[Room] = []
    openings: list[Opening] = []
    obstacles: list[Obstacle] = []

class Room:
    id: ID
    name: str
    vertices: list[Vertex]          # >= 3, world cm, normalised to clockwise on screen
    color: str | None = None        # "#rrggbb"

class DoorSpec:
    hinge: Literal["start", "end"]
    swing: Literal["in", "out"]

class Opening:
    id: ID
    kind: Literal["door", "window", "opening"]
    room_id: ID
    edge_start_vertex_id: ID        # edge runs from this vertex to the next
    offset: float                   # cm, edge start -> opening centre, >= 0
    width: float                    # cm, > 0
    door: DoorSpec | None = None    # required when kind == "door", else None

# Shapes are centred on / relative to the item's local origin.
class RectShape:    type: Literal["rect"];    width: float; depth: float   # > 0
class EllipseShape: type: Literal["ellipse"]; rx: float; ry: float         # > 0
class PolygonShape: type: Literal["polygon"]; points: list[Point]          # >= 3
Shape = Annotated[RectShape | EllipseShape | PolygonShape, Field(discriminator="type")]

class Placed:
    id: ID
    name: str
    shape: Shape
    x: float; y: float              # world position of the local origin
    rotation: float = 0             # degrees clockwise, normalised to [0, 360)
    color: str | None = None
    notes: str | None = None

class Obstacle(Placed): pass

class FurnitureMeta:
    product: str | None = None
    url: str | None = None
    price: float | None = None

class FurnitureItem(Placed):
    category: str | None = None
    room_id: ID | None = None
    locked: bool = False
    group_id: ID | None = None
    clearance: float | None = None  # cm kept free around the item; None: no zone
    meta: FurnitureMeta | None = None

class Group: id: ID; name: str

class Layout:
    id: ID
    name: str
    furniture: list[FurnitureItem] = []
    groups: list[Group] = []

class BackgroundImage:
    asset_id: ID                    # file assets/<asset_id>.<ext> in the archive
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    origin: Point                   # world position of the image's top-left
    cm_per_pixel: float             # > 0
    rotation: float = 0
    opacity: float = 0.5            # 0..1
    visible: bool = True
    locked: bool = True
```

**Document-level validation:** IDs are unique within the project; there is at
least one layout; `active_layout_id` exists; openings reference an existing
room and one of its vertices; `door` is set exactly when `kind == "door"`;
`group_id`s exist in their layout; `room_id`s exist.

**Not persisted:** viewport, selection, active tool, undo history, findings,
save status.

**Migrations:** `persistence/migrations/` holds one function per version step
(`v1_to_v2`, …) that works on raw dicts. Every past schema version keeps at
least one fixture file in `tests/fixtures/`, and a test loads every fixture
through the current loader. Breaking a fixture is a failing test.

## 12. Editor state and undo / redo

- Pure-Python `EditorState` (no Qt) holds the current `ProjectDoc`, the
  selection and the history. The Qt layer observes it through a small signal
  adapter.
- Every committed action produces a new document. The previous document goes
  onto the undo stack (copy-on-write snapshots; documents are small). Limit:
  200 steps per session, not persisted.
- One user action is one history entry: a drag commits once on release, not on
  every mouse move. A numeric field commits on Enter or focus-out.
- During a drag, canvas items move visually; on release the new values are
  computed in world coordinates and committed, and the scene re-syncs from the
  document.
- Switching layouts is not an undoable action; edits inside a layout are.
  The project name and settings (units, grid, snapping, apartment lock) are
  not undoable either: undo and redo keep their current values.

## 13. Visual design

A clean technical drawing using the Qt Fusion style with a forced light
palette: light neutral background, subtle grid (minor and major lines), dark
room outlines, soft room fills, furniture in muted fills with darker outlines.
Doors and windows each have a distinct conventional symbol. Selection is a thin
accent outline with small square handles. Red is reserved for collisions and
amber for warnings. Precision and legibility come before decoration. Light
theme only for the MVP.

## 14. Out of scope

AI or LLM features; accounts, backend or sync service; real-time
collaboration; web or mobile versions; 3D; photorealistic models; floor-plan
recognition; curved furniture geometry; retailer integrations; multiple
storeys; wall thickness and construction-grade validation; vertical clearance.

**Parked for later:** Plan/Furnish modes, measuring tape tool, furniture preset
library, dark theme, auto-update.

## 15. Milestones

1. **Foundation.** uv project, package layout, pydantic model with
   document-level validation, geometry module with tests, layering test, and an
   empty main window that launches.
2. **Persistence.** Project file read/write, migrations and fixtures, atomic
   autosave with retries and `.bak`, lock files, conflict detection, start
   screen and project management.
3. **Canvas and rooms.** View zoom/pan, grid and snapping, rectangle and
   polygon rooms, vertex editing, numeric editing, validation, undo/redo,
   apartment lock.
4. **Furniture.** Shapes, transform handles, multi-select, groups, custom
   polygon drawing, layouts, keyboard shortcuts.
5. **Openings and obstacles.** Doors (with swing), windows, openings,
   obstacles.
6. **Fit checks.** Findings engine, highlighting, warnings panel, distance
   readouts, clearance zones.
7. **Finish.** Background image with calibration, plan PNG/PDF export,
   PyInstaller builds, visual polish.

Each milestone ends with a working app and passing tests.

## 16. Acceptance criteria

- Multiple rooms with accurate interior dimensions; adjacent rooms share
  edges.
- Doors (with swing), windows and obstacles can be added and stay attached
  when rooms are edited.
- Furniture of every shape can be added, sized numerically and manipulated
  directly; custom polygons can be drawn and edited.
- Several layouts per project; switching layouts keeps the apartment intact.
- Fit checks find overlaps, wall crossings, obstacle hits and blocked door
  swings, and furniture flush against a wall is not flagged.
- Zoom, pan and rotation never change stored dimensions (tested).
- Projects reopen exactly as saved: save → load deep-equals the document, with
  identical image bytes.
- Create, open, rename, duplicate and delete projects all work from the start
  screen.
- A failed save, a locked file, an external change or an invalid file each
  produce a clear message and never destroy the last good file.
- Plans export to PNG and PDF.
- The app runs on Windows and macOS from source (`uv run`) and as a packaged
  build.
