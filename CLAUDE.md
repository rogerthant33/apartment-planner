# Apartment Planner

A private, browser-only 2D apartment planner for two people. The full scope,
data model and milestones are in [docs/SPEC.md](docs/SPEC.md). Read the
relevant section before starting a feature, and update the spec in the same
change when behaviour or scope changes.

## Stack

Vite + React + TypeScript (strict), react-konva, zustand + immer, idb, zod,
vitest (+ fake-indexeddb). npm is the package manager. Development happens on
Windows, so keep scripts cross-platform (no POSIX-only shell in
`package.json`).

## Commands

> Fill these in at scaffold time (milestone 1) and keep them accurate.

- `npm run dev`: start the dev server
- `npm test`: run unit tests once (vitest run)
- `npm run typecheck`: `tsc --noEmit`
- `npm run lint`: eslint
- `npm run build`: production build

Before calling work done, run `npm run typecheck` and `npm test`.

## Architecture

```
src/
  model/        types, zod schema, defaults, id helpers   (pure)
  geometry/     points, polygons, transforms, distances   (pure)
  fit/          fit-check findings from apartment + layout (pure)
  persistence/  idb access, autosave, export/import, migrations/
  store/        zustand store, undo history (immer patches)
  editor/       react-konva canvas, viewport, tools, handles
  ui/           sidebars, panels, dialogs
tests/fixtures/ exported files for each schema version
```

**Layering:** `model`, `geometry` and `fit` must not import React, Konva,
zustand or browser APIs. `persistence` must not import React or Konva. UI and
editor code read from the store and call actions; they never mutate the
document directly.

## Invariants (don't break these)

- **The `ProjectDoc` is the source of truth.** Konva nodes are views. Never read
  geometry back from Konva nodes; Konva node state isn't stored anywhere.
- **World units are cm**, +y down, rotation in degrees clockwise. Convert
  screen↔world only at the input boundary, via the viewport transform.
  Geometry, snapping and fit checks take world coordinates only.
- **No wall thickness.** Rooms are interior polygons; walls are their edges.
- **Openings reference `edgeStartVertexId`, never an edge index.**
- **One user gesture = one undo entry.** Commit on pointer-up or input
  blur/Enter, not on every move.
- **Collisions use `EPS` (0.1 cm).** Touching is not overlapping.
- **Persisted shape changes need a schema migration.** Follow the
  `schema-change` skill.
- **Never write base64 into IndexedDB.** Images are Blobs in the `assets` store.
- **Never lose the last good save.** Save errors are surfaced and retried,
  never swallowed.
- No network calls at runtime. Everything works offline after the first load.

## Conventions

- Prefer small pure functions with unit tests over logic inside components.
- Geometry and persistence code is written test-first, or at least with its
  tests in the same change.
- IDs come from `crypto.randomUUID()` via `src/model/ids.ts`.
- Name things in domain terms (room, opening, layout, furniture, obstacle) as
  the spec uses them.
- User-facing messages say what happened and how to fix it, plainly, without
  apologising.
