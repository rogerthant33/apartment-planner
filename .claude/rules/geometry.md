---
paths:
  - "src/apartment_planner/geometry/**"
  - "src/apartment_planner/fit/**"
  - "tests/geometry/**"
  - "tests/fit/**"
---

# Geometry and fit-check rules

- Pure functions only: no PySide6, no I/O, no clocks. Never mutate inputs;
  pydantic models in, new values or Shapely geometries out.
- All inputs and outputs are world coordinates in cm. Anything involving view
  or screen coordinates belongs in `canvas/`.
- Build Shapely geometry from model objects only through the helpers in
  `geometry/shapes.py` (`placed_polygon`, `room_polygon`) and
  `geometry/polygon.py` (`points_polygon`). Don't call `shapely.affinity` ad
  hoc elsewhere.
- Use `geometry.constants.EPS` and the shared `overlaps()` / `outside()` /
  `is_substantial()` helpers for every tolerance decision. No literal epsilons.
- Relation helpers assume valid polygons and don't re-check. Validate each
  footprint once (`validate_polygon`) when building it for a check run, and
  report invalid ones as findings.
- Build expensive shared geometry (such as the union of rooms) once per check
  run, not per pair.
- `geometry/polygon.py`, `overlap.py`, `transform.py` and `constants.py` are
  imported by `model`, so they must not import `apartment_planner.model`.
- Import from submodules (`geometry.shapes`, `geometry.overlap`, ...). The
  package `__init__` stays empty.
- Treat polygons as possibly concave. Bounding boxes are only an early-out.
- Every public function has tests covering:
  - a normal case
  - touching or flush edges (must not count as overlap)
  - degenerate input (zero-length edge, collinear points, < 3 vertices)
  - rotated input (at least 0°, 90° and an arbitrary angle like 37°)
- Use hypothesis for round-trip and invariance properties (for example,
  local→world→local, or area unchanged by rotation).
- Fit checks return data (`Finding`s with severity, kind, involved IDs and a
  message). They never raise on bad geometry; they report it.
