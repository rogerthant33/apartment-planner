"""Fitting a plan onto paper: drawing scales and scale bars. See docs/SPEC.md §9."""

import math

MM_PER_CM = 10.0


def fits_at(content_cm: tuple[float, float], area_mm: tuple[float, float], scale: int) -> bool:
    """True if `content_cm` drawn at 1:`scale` fits in `area_mm`."""
    width, height = (side * MM_PER_CM / scale for side in content_cm)
    return width <= area_mm[0] and height <= area_mm[1]


def scale_bar_length(longest_cm: float) -> float:
    """The longest round length (1, 2 or 5 times a power of ten cm) up to `longest_cm`,
    and at least 1 cm."""
    longest = max(longest_cm, 1.0)
    power = 10.0 ** math.floor(math.log10(longest))
    if power > longest:  # log10 rounds up just below a power of ten
        power /= 10
    return next(step * power for step in (5, 2, 1) if step * power <= longest)
