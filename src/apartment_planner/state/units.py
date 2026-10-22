"""Formatting and parsing lengths in the display unit. Values are always cm."""

import re
from typing import Literal

Unit = Literal["mm", "cm", "m"]

CM_PER_UNIT: dict[str, float] = {"mm": 0.1, "cm": 1.0, "m": 100.0}
_DECIMALS: dict[str, int] = {"mm": 0, "cm": 1, "m": 3}
_LENGTH = re.compile(r"^\s*(\d+(?:[.,]\d*)?|[.,]\d+)\s*(mm|cm|m)?\s*$", re.IGNORECASE)


def format_length(cm: float, unit: Unit) -> str:
    """E.g. "250 cm", "2.5 m", "2505 mm": rounded for the unit, without trailing zeros."""
    text = f"{cm / CM_PER_UNIT[unit]:.{_DECIMALS[unit]}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text} {unit}"


def parse_length(text: str, unit: Unit) -> float | None:
    """cm from "2.5", "2,5 m", "250cm" and the like, or None if it isn't a length.

    A number without a unit is in the display unit.
    """
    match = _LENGTH.match(text)
    if match is None:
        return None
    value = float(match[1].replace(",", "."))
    return value * CM_PER_UNIT[(match[2] or unit).lower()]


def format_area(cm2: float) -> str:
    return f"{cm2 / 10_000:.2f} m²"
