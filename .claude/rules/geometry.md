---
paths:
  - "src/geometry/**"
  - "src/fit/**"
---

# Geometry and fit-check rules

- Pure functions only: no React, Konva, zustand, DOM, or `Date`. Inputs are
  never mutated.
- All inputs and outputs are world coordinates in cm. If a function needs
  screen space, it belongs in `src/editor/`, not here.
- Use the shared `EPS` constant (0.1 cm) for every tolerance comparison. Don't
  sprinkle literal epsilons.
- Treat polygons as possibly concave. Don't use SAT or bounding-box shortcuts
  as the final answer, only as an early-out.
- Ellipses become polygons through the single shared helper (48 segments) so
  rendering-independent checks are consistent.
- Every exported function has unit tests covering:
  - a normal case
  - touching or flush edges (must not count as overlap)
  - degenerate input (zero-length edge, collinear points, < 3 vertices)
  - rotated input (at least 0°, 90°, and an arbitrary angle like 37°)
- Fit checks return data (`Finding[]` with severity, kind, involved IDs, and a
  message). They never throw on bad geometry; they report it.
