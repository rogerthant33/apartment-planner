---
name: schema-change
description: Procedure for changing the persisted project format of the apartment planner (pydantic models in src/apartment_planner/model, project.json contents, or the .apartment ZIP layout). Use whenever adding, removing, renaming or retyping a persisted field, or changing how files are packaged.
---

# Changing the persisted schema

The file format is a promise to users: every `.apartment` file they have must
keep opening. Follow these steps in order.

## 1. Decide whether it's breaking

- **Additive with a default** (a new field whose default reproduces the old
  behaviour exactly): no version bump is needed. Add the field with a default,
  check that every reader handles it, then skip to step 4.
- **Anything else** (a required field, a rename, a type change, a removal, a
  semantics change, or an archive layout change): bump the version and follow
  every step.

## 2. Freeze a fixture of the current version first

If `tests/fixtures/` lacks a realistic fixture for the current version `N`,
create one before changing any code. Include rooms with openings (a door and a
window), an obstacle, two layouts, every shape type, a group, and a background
image. Save it as `tests/fixtures/v<N>_<description>.apartment`. Generate it
with the current save code, not by hand.

## 3. Bump and migrate

- Increment `CURRENT_SCHEMA_VERSION` in `model/`.
- Add `persistence/migrations/v<N>_to_v<N+1>.py` with
  `def migrate(data: dict[str, Any]) -> dict[str, Any]`. It works on raw dicts
  and must never import the current models, which will keep changing.
- Register it in `persistence/migrations/__init__.py` so `migrate_to_current()`
  runs each step in sequence.
- If assets move or are renamed, the migration step also receives and returns
  the asset mapping. Keep that in the same module.
- Update the pydantic models to the new shape.

## 4. Tests (all must pass)

- A migration unit test: old fixture data → migrated dict matches
  expectations.
- The fixture test loads **every** file in `tests/fixtures/` through the normal
  loader and validates it.
- Save → load of a current-version project deep-equals the original,
  including asset bytes.

## 5. Docs

Update the data model section of `docs/SPEC.md` (§11) in the same change.
