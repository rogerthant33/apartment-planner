"""Fitting a plan onto paper: drawing scales and scale bars. See docs/SPEC.md §9."""

import math
from collections.abc import Sequence

MM_PER_CM = 10.0


def fits_at(content_cm: tuple[float, float], area_mm: tuple[float, float], scale: int) -> bool:
    """True if `content_cm` drawn at 1:`scale` fits in `area_mm`."""
    width, height = (side * MM_PER_CM / scale for side in content_cm)
    return width <= area_mm[0] and height <= area_mm[1]


def fitting_scale(
    content_cm: tuple[float, float], area_mm: tuple[float, float], scales: Sequence[int]
) -> int | None:
    """The first of `scales` (1:N) at which the content fits; None if none does."""
    return next((scale for scale in scales if fits_at(content_cm, area_mm, scale)), None)


def scale_bar_length(longest_cm: float) -> float:
    """The longest round length (1, 2 or 5 times a power of ten cm) up to `longest_cm`,
    and at least 1 cm."""
    if longest_cm <= 1:
        return 1.0
    power = 10.0 ** math.floor(math.log10(longest_cm))
    return next(step * power for step in (5, 2, 1) if step * power <= longest_cm)
