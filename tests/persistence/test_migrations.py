from typing import Any

from apartment_planner.persistence.migrations import Step, migrate


def add_step(n: int) -> Step:
    def step(data: dict[str, Any]) -> dict[str, Any]:
        return {**data, "steps": [*data["steps"], n]}

    return step


STEPS = {1: add_step(1), 2: add_step(2), 3: add_step(3)}


def test_runs_each_step_from_the_file_version_to_the_target_in_order() -> None:
    assert migrate({"steps": []}, 1, steps=STEPS, target=4) == {"steps": [1, 2, 3]}
    assert migrate({"steps": []}, 2, steps=STEPS, target=3) == {"steps": [2]}
    assert migrate({"steps": []}, 3, steps=STEPS, target=3) == {"steps": []}
