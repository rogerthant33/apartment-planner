---
name: schema-change
description: Procedure for changing the persisted project format (ProjectDoc, export file, or IndexedDB stores) in the apartment planner. Use whenever adding, removing, renaming or retyping a field in src/model types or zod schema, changing the export file shape, or changing IndexedDB stores/indexes.
---

# Changing the persisted schema

The persisted format is a promise to users: every file they exported must keep
importing. Follow these steps in order.

## 1. Decide whether it's breaking

- **Additive and optional** (a new optional field, with absence meaning the
  old behaviour): no version bump is needed. Update the type and the zod
  schema, and make sure absence is handled everywhere the field is read. Skip
  to step 5.
- **Anything else** (a required field, a rename, a type change, a removal, or
  a semantics change): bump the version and follow every step.

## 2. Freeze a fixture of the current version first

If `tests/fixtures/` has no realistic fixture for the current version
`N`, export one before changing any code: rooms with openings (door, window),
an obstacle, two layouts, each shape type, a group, and a background image.
Save it as `tests/fixtures/vN-<description>.apartment.json`.

## 3. Bump and migrate

- Increment `CURRENT_SCHEMA_VERSION` in `src/model/`.
- Add `src/persistence/migrations/vN-to-vN+1.ts`. It's a pure function from
  the old document to the new one. Type its input loosely (the old shape) and
  never import the current types for the input side.
- Register it in the migrations index so `migrate()` runs steps in sequence.
- Change the types and the zod schema to the new shape.

## 4. IndexedDB

If stores or indexes change, bump the idb database version and add an
`upgrade` branch. Existing records in `projects` must also be migrated, either
during the upgrade or lazily on load through the same `migrate()` path. Lazy is
preferred so there's only one migration codepath.

## 5. Tests (all must pass)

- A migration unit test: old fixture → migrated doc matches expectations.
- The fixture round-trip test loads **every** file in `tests/fixtures/`
  through import and validates it against the current schema.
- Export → import of a current-version project deep-equals the original
  (except the new project ID).

## 6. Docs

Update the data model section of `docs/SPEC.md` (§11) in the same change.
