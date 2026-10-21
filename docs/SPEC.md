# Apartment Planner — MVP Specification (v2)

This is the source of truth for scope. It revises the original brief. When the
code and this document disagree, fix one of them; don't let them drift.

## 1. Overview

A private, browser-based 2D apartment planner for two people. Draw the
apartment's rooms using interior measurements, add doors, windows and fixed
obstacles, then try out several furniture layouts and check what fits.

**Principles**

- Accurate real-world dimensions; the screen is only a view.
- Simple, direct editing with immediate visual feedback.
- Never lose work: automatic local saving, visible save status, easy backups.
- Fully local: no backend, accounts, AI, or network dependency after first load.

**Changes from the original brief**

- **No wall thickness.** Rooms are interior floor polygons, which is what you
  measure with a tape. Walls are the polygon edges.
- **Multiple furniture layouts per apartment.** Apartment geometry is shared;
  each layout holds its own furniture.
- **One export format:** a single `.apartment.json` file with images embedded.
  No ZIP.
- **Additions:** door swing arcs count in fit checks, keyboard shortcuts, plan
  export (PNG / print-to-PDF), offline support via a service worker, persistent
  storage requests, backup reminders, single-tab editing locks.

## 2. Technology

| Concern | Choice |
| --- | --- |
| App | Vite + React + TypeScript (strict) |
| Canvas | Konva via react-konva (presentation only) |
| State / undo | zustand + immer (patches for history) |
| Persistence | IndexedDB via `idb` |
| Validation / migration | zod |
| Polygon booleans | `polygon-clipping` (or a maintained fork; check before adding) |
| Offline | `vite-plugin-pwa` (precache app shell) |
| Tests | vitest, `fake-indexeddb` for persistence; Playwright (Node) for E2E later |

All other geometry primitives are written in-house in `src/geometry/` and unit
tested.

## 3. Interface

Desktop-first, three columns.

- **Left sidebar:** project menu (new, open, rename, duplicate, delete, import,
  export), layout switcher (add, rename, duplicate, delete layouts), tools,
  object list with visibility toggles.
- **Canvas:** grid, rooms, openings, obstacles, furniture, dimension labels,
  warnings. Zoom, pan, selection, drag, resize, rotate.
- **Right sidebar:** properties of the selection (numeric dimensions, position,
  rotation, label, color, notes, metadata), actions (duplicate, delete, lock,
  group), and the warnings list for the current layout.
- **Top bar:** undo/redo, save status (Saving… / Saved / Save failed —
  retrying), "Apartment locked" toggle, export plan.

A persistent, dismissible notice explains that projects live in this browser
only and that exports are the backup. Show "Last exported: …" per project and
a gentle reminder when it's more than 14 days old (or never) and the project has
changed since.

## 4. Coordinates and units

- World units are **centimetres**, stored as floats. +x right, +y down (matches
  the canvas). Rotation is in **degrees, clockwise**, about the object's origin.
- One viewport transform (`scale`, `offsetX`, `offsetY`) maps world↔screen.
  Zoom and pan only change the viewport, never the document.
- All geometry, snapping and fit checks run in world coordinates. Screen
  coordinates are converted at the input boundary and nowhere else.
- Display unit: mm / cm / m. It only affects formatting and parsing of input.
- Grid size is configurable (default 10 cm). Snapping can be toggled; hold
  Alt to suspend it during a drag.
- Dimension labels use a constant screen size regardless of zoom.

## 5. Apartment editor

### Rooms

- Draw rectangular rooms (drag) or polygon rooms (click points, close on the
  first point or with Enter).
- Edit vertices by dragging; edit edge lengths numerically (the edge's end
  vertex moves along the edge direction).
- Insert a vertex on an edge (double-click); delete a vertex (select + Delete,
  minimum 3).
- Add, rename, duplicate, delete rooms. Each room has a name label at its
  centroid and shows its area.
- Adjacent rooms share boundaries by snapping vertices and edges together.
  There is no wall graph: each room owns its polygon.
- Vertex snapping: to other rooms' vertices, then to their edges, then to the
  grid.

### Validation

A room or polygon is valid when it has ≥ 3 vertices, no self-intersections, no
edge shorter than 1 cm, and positive area. Invalid edits show a red preview
while dragging and **revert on release** with a message saying why. Numeric
input that would produce invalid geometry is rejected inline. Overlapping
rooms are allowed but produce a warning.

### Doors and windows (openings)

- Placed on a room edge, referenced by `roomId` + `edgeStartVertexId` + `offset`
  (cm from the edge start to the opening's centre) + `width`.
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

### Fixed obstacles

Columns, built-in cupboards, radiators and so on. Same shape model as
furniture, but they belong to the apartment (shared across layouts) and are
edited only while the apartment is unlocked.

### Apartment lock

When locked (the default once rooms exist), rooms, openings and obstacles can't
be selected or moved, so furniture arranging can't disturb them.

## 6. Furniture

### Shapes

- `rect` (width × depth), `ellipse` (rx, ry; circle when equal), `polygon`
  (local-coordinate points). L-shapes are polygons; include an "L-shape"
  template that generates one from four dimensions.
- The model keeps a discriminated `type` so curved segments can be added later
  as a new shape type without migrating old data.

### Properties

`id`, `name`, `category?`, `shape`, `x`, `y` (world position of the local
origin), `rotation`, `color?`, `notes?`, `roomId?`, `locked`, `groupId?`,
`clearance?` (cm, overrides the project default), `meta?` (`product`, `url`,
`price`).

### Manipulation

- Select (click, Shift+click, marquee), drag, move multiple selected items.
- Resize with handles or numeric input; rotate with a handle (snaps to 15°
  increments, hold Alt for free rotation) or numeric input.
- Duplicate, delete, rename, group/ungroup (groups select and move together),
  lock.
- Snap to grid, to room edges (flush against a wall), and to other items'
  edges.

### Custom polygon drawing

Click points; close on the first point or with Enter; Escape cancels. Show
edge lengths while drawing and after creation. Edit vertices by dragging or
numerically. Validated like rooms.

### Keyboard shortcuts

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

Shortcuts are ignored while focus is in a text input.

## 7. Fit checking

Pure functions in `src/fit/` that take the apartment plus a layout and return a
list of findings. Recomputed (memoised) whenever the apartment or the active
layout changes.

**Tolerance.** Touching, or overlapping by less than 1 mm (`EPS = 0.1` cm), is
not a collision, so furniture flush against a wall or another item doesn't
trigger a warning.

**Curves.** Ellipses are approximated as 48-gons for checks. Rendering uses the
true shape.

| Check | Severity |
| --- | --- |
| Furniture overlaps furniture | collision |
| Furniture overlaps an obstacle | collision |
| Furniture not contained in the union of rooms (crosses a wall or sits outside) | collision |
| Furniture intersects a door's swing area | collision |
| Furniture blocks a doorway or opening (within `clearance` depth on either side) | warning |
| Item's clearance zone intersects another item, obstacle or wall | warning |
| Rooms overlap each other | warning |

- Clearance is measured as minimum polygon-to-polygon distance, which is exact
  and needs no offsetting. The clearance zone is drawn as a translucent
  rounded outline (wide stroke with round joins) behind the item.
- Collisions are red, warnings amber. Affected items are outlined; the
  right-sidebar list explains each finding, and clicking one selects the items.
- Selecting two items shows the minimum distance between them. Selecting one
  item shows its distance to the nearest wall on each side (left, right, up,
  down along its rotated axes).
- Nothing is ever blocked. Findings are informational.

## 8. Local storage

### IndexedDB layout (`apartment-planner` database)

| Store | Key | Value |
| --- | --- | --- |
| `projects` | `id` | `ProjectDoc` |
| `assets` | `[projectId, assetId]` | `{ projectId, assetId, blob, mimeType, width, height }` |
| `meta` | `key` | small app-level records (e.g. `lastExportAt:<projectId>`) |

Images are stored as Blobs once and never rewritten by autosave.

### Project management

New, rename, open, duplicate (copies assets), delete (with confirmation;
deletes assets). The project list shows name and last-modified time, newest
first.

### Autosave

- The store updates immediately. Persistence is debounced at **750 ms** after
  the last change.
- At most one write is in flight. Changes made during a write schedule another
  write when it finishes, so the latest state always wins.
- On failure: status shows "Save failed — retrying", then retries with backoff
  (1 s, 2 s, 5 s, then every 10 s). In-memory state is kept. IndexedDB
  transactions are atomic, so the last good version stays intact.
- Flush immediately on `visibilitychange` → hidden and on manual Save
  (Ctrl+S). Warn on `beforeunload` while a save is pending or failing.
- **Single-tab editing:** acquire a Web Lock (`navigator.locks`) named after
  the project ID. If another tab holds it, open read-only with an explanation.

### Durability

- Call `navigator.storage.persist()` after the first project is created and
  show the result in settings ("Storage: persistent / may be cleared by the
  browser").
- Explain the browser-local limitation in the UI (see §3).

## 9. Export and import

### Plan file: `<name>.apartment.json`

```json
{
  "format": "apartment-planner",
  "schemaVersion": 1,
  "exportedAt": "2026-10-21T12:00:00.000Z",
  "project": { "...": "ProjectDoc" },
  "assets": {
    "<assetId>": { "mimeType": "image/png", "width": 2000, "height": 1400, "data": "<base64>" }
  }
}
```

- Contains everything needed to rebuild the project. No viewport, selection,
  undo history or derived geometry.
- Base64 exists only in the export file, never in IndexedDB.

### Import

1. Parse JSON. Check that `format` matches and `schemaVersion` ≤ the app's
   current version; reject newer versions with "This file was made by a newer
   version".
2. Run migrations one version at a time to the current version, then validate
   with the current zod schema. Errors name the failing path.
3. Ask the user: **Import as new project** (default), or **Replace** an existing
   project with the same ID if one exists (with confirmation).
4. A new import gets a new project ID. Entity IDs inside the project are kept,
   because they only need to be unique within a project. Assets are stored
   under the new project ID.

### Plan image export

- **PNG:** render the active layout (rooms, labels, dimensions, openings,
  furniture, plus a scale bar and title) off-screen at 2× pixel ratio, fitted to
  the content bounds. Warnings are optional and off by default.
- **PDF:** a print view of the same rendering with a print stylesheet, via the
  browser's print dialog ("Save as PDF"). No PDF library.

## 10. Background floor-plan image

- Import a PNG, JPG or WebP image and store it as an asset Blob.
- **Two-point calibration:** click two points on the image and enter the real
  distance between them. Then position (drag) and optionally rotate the image.
- Opacity, visibility and lock controls. Rooms can be traced over it.
- Calibration is saved in the project. The image travels in exports.

## 11. Data model (schema v1)

```ts
type ID = string;                    // crypto.randomUUID()
interface Point { x: number; y: number }

interface ProjectDoc {
  schemaVersion: 1;
  id: ID;
  name: string;
  createdAt: string;                 // ISO 8601
  updatedAt: string;
  settings: ProjectSettings;
  apartment: Apartment;
  layouts: Layout[];                 // at least one
  activeLayoutId: ID;
  background?: BackgroundImage;
}

interface ProjectSettings {
  displayUnit: 'mm' | 'cm' | 'm';
  gridSize: number;                  // cm
  snapEnabled: boolean;
  defaultClearance: number;          // cm, default 60
  apartmentLocked: boolean;
}

interface Apartment {
  rooms: Room[];
  openings: Opening[];
  obstacles: Obstacle[];
}

interface Room {
  id: ID;
  name: string;
  vertices: Vertex[];                // world coords, normalised to clockwise on screen
  color?: string;
}
interface Vertex extends Point { id: ID }

interface Opening {
  id: ID;
  kind: 'door' | 'window' | 'opening';
  roomId: ID;
  edgeStartVertexId: ID;             // edge runs from this vertex to the next
  offset: number;                    // cm, edge start → opening centre
  width: number;                     // cm
  door?: { hinge: 'start' | 'end'; swing: 'in' | 'out' };
}

type Shape =
  | { type: 'rect'; width: number; depth: number }          // centred on origin
  | { type: 'ellipse'; rx: number; ry: number }             // centred on origin
  | { type: 'polygon'; points: Point[] };                   // local coords

interface Placed {
  id: ID;
  name: string;
  shape: Shape;
  x: number; y: number;              // world position of the local origin
  rotation: number;                  // degrees clockwise
  color?: string;
  notes?: string;
}

interface Obstacle extends Placed {}

interface FurnitureItem extends Placed {
  category?: string;
  roomId?: ID;
  locked: boolean;
  groupId?: ID;
  clearance?: number;                // cm, overrides settings.defaultClearance
  meta?: { product?: string; url?: string; price?: number };
}

interface Layout {
  id: ID;
  name: string;
  furniture: FurnitureItem[];
  groups: { id: ID; name: string }[];
}

interface BackgroundImage {
  assetId: ID;
  origin: Point;                     // world position of the image's top-left
  cmPerPixel: number;
  rotation: number;                  // degrees clockwise
  opacity: number;                   // 0..1
  visible: boolean;
  locked: boolean;
}
```

**Not persisted:** viewport, selection, active tool, undo history, fit
findings, save status.

**Migrations:** `src/persistence/migrations/` holds one function per version
step (`v1→v2`, …). Every past schema version keeps at least one fixture file in
`tests/fixtures/`, and a test loads every fixture through the current import
path. Breaking a fixture is a failing test.

## 12. Undo / redo

- History covers the `ProjectDoc` only, as immer patch pairs, for the session
  (not persisted). Limit 200 steps.
- One user action is one history entry: a drag records once on release, not
  on every pointer move. A numeric field commits on blur or Enter.
- Switching layouts is not an undoable action; edits inside a layout are.

## 13. Visual design

A clean technical drawing: light neutral background, subtle grid (minor and
major lines), dark room outlines, soft room fills, furniture in muted fills
with darker outlines. Doors and windows each have a distinct conventional
symbol. Selection is a thin accent outline with small square handles. Red is
reserved for collisions and amber for warnings. Precision and legibility come
before decoration. Light theme only for the MVP.

## 14. Out of scope

AI or LLM features; accounts, backend or sync; real-time collaboration; 3D;
photorealistic models; floor-plan recognition; curved furniture geometry;
retailer integrations; multiple storeys; wall thickness and construction-grade
validation; vertical clearance.

**Parked for later:** Plan/Furnish modes, measuring tape tool, furniture preset
library, dark theme.

## 15. Milestones

1. **Foundation.** Scaffold, data model and zod schema, geometry module with
   tests.
2. **Persistence.** IndexedDB stores, project management, autosave state
   machine, export/import with migrations and fixtures. Tests use
   `fake-indexeddb`.
3. **Canvas and rooms.** Viewport, grid and snapping, rectangle and polygon
   rooms, vertex editing, numeric editing, validation, undo/redo, apartment
   lock.
4. **Furniture.** Shapes, transform handles, multi-select, groups, custom
   polygon drawing, layouts, keyboard shortcuts.
5. **Openings and obstacles.** Doors (with swing), windows, openings,
   obstacles.
6. **Fit checks.** Findings engine, highlighting, warnings panel, distance
   readouts, clearance zones.
7. **Finish.** Background image with calibration, plan PNG/PDF export, PWA
   offline, persistent storage, backup reminders, visual polish.

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
- Projects survive closing and reopening the browser. Create, rename,
  duplicate, open and delete all work.
- Export → import round-trips to a deep-equal `ProjectDoc` (apart from the new
  project ID) with identical image bytes.
- Failed saves and invalid imports surface clear messages and never destroy
  the last good data.
- After one online load, the app reloads and works offline.
- The plan exports to PNG and prints to PDF.
