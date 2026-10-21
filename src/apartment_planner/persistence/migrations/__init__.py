"""Schema migrations, one step per version: STEPS[n] turns version n into n + 1.

Steps work on raw dicts (the `project` object from project.json) and must never
import the current models. See the schema-change skill.
"""

from collections.abc import Callable, Mapping
from typing import Any

from apartment_planner.model.project import CURRENT_SCHEMA_VERSION

Step = Callable[[dict[str, Any]], dict[str, Any]]

STEPS: dict[int, Step] = {}


def migrate(
    data: dict[str, Any],
    version: int,
    *,
    steps: Mapping[int, Step] = STEPS,
    target: int = CURRENT_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Run each step from `version` up to `target`."""
    for current in range(version, target):
        data = steps[current](data)
    return data
