---
paths:
  - "src/apartment_planner/canvas/**"
  - "src/apartment_planner/ui/**"
  - "tests/canvas/**"
  - "tests/ui/**"
---

# Canvas and UI rules

- Scene coordinates are world cm. Never apply scale factors to item geometry;
  zoom and pan only change the view transform.
- Items render from the document. Never read positions or shapes back from
  items into the model. On mouse release, compute the new values in world
  coordinates from the gesture, commit them through `EditorState`, and let the
  scene re-sync.
- During a drag, show a live preview only. Exactly one commit per gesture.
- Labels and handles that should keep a constant screen size use
  `ItemIgnoresTransformations`. Don't compensate by hand with the zoom level.
- Keep Qt classes thin: put snapping, hit-test maths and value calculations in
  pure functions (`geometry/` or `state/`) with unit tests.
- Use `QKeySequence.StandardKey` for standard shortcuts so macOS gets Cmd.
- UI tests use pytest-qt (`qtbot`) with the offscreen platform. Test behaviour
  through `EditorState` and signals, not pixels.
