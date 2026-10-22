import pytest

from apartment_planner.persistence.autosave import Autosave, SaveStatus


def failing(times: int) -> tuple[Autosave, list[float]]:
    """An Autosave whose save failed `times` times in a row, and each retry delay."""
    autosave = Autosave()
    autosave.changed(0.0)
    delays = []
    now = 0.75
    for _ in range(times):
        autosave.started()
        autosave.failed(now, "No space left on device")
        assert autosave.deadline is not None
        delays.append(autosave.deadline - now)
        now = autosave.deadline
    return autosave, delays


def test_saves_750_ms_after_the_last_change() -> None:
    autosave = Autosave()
    autosave.changed(0.0)
    autosave.changed(0.5)

    assert autosave.status is SaveStatus.PENDING
    assert not autosave.due(1.249)
    assert autosave.due(1.25)
    assert autosave.due(9.0)  # a timer that fires late still saves


def test_nothing_is_due_without_changes() -> None:
    autosave = Autosave()

    assert not autosave.unsaved
    assert not autosave.due(100.0)


def test_successful_save_without_new_changes_is_saved() -> None:
    autosave = Autosave()
    autosave.changed(0.0)
    autosave.started()
    assert autosave.unsaved

    autosave.succeeded(1.0)

    assert autosave.status is SaveStatus.SAVED
    assert not autosave.unsaved
    assert autosave.deadline is None


@pytest.mark.parametrize(("finished", "next_save"), [(1.2, 1.75), (3.0, 3.0)])
def test_change_during_a_save_triggers_another_save_after_it(
    finished: float, next_save: float
) -> None:
    autosave = Autosave()
    autosave.changed(0.0)
    autosave.started()
    autosave.changed(1.0)
    assert autosave.deadline is None  # only one save at a time

    autosave.succeeded(finished)

    assert autosave.status is SaveStatus.PENDING
    assert autosave.deadline == next_save


def test_retries_after_1_2_and_5_seconds_then_every_10() -> None:
    autosave, delays = failing(5)

    assert delays == [1, 2, 5, 10, 10]
    assert autosave.status is SaveStatus.FAILED
    assert autosave.error == "No space left on device"
    assert autosave.unsaved


def test_changes_while_failing_keep_the_retry_schedule() -> None:
    autosave, _ = failing(3)
    deadline = autosave.deadline

    autosave.changed(1000.0)

    assert autosave.status is SaveStatus.FAILED
    assert autosave.deadline == deadline


def test_success_after_failures_clears_the_error_and_the_backoff() -> None:
    autosave, _ = failing(3)
    autosave.started()
    autosave.succeeded(100.0)
    assert (autosave.status, autosave.error) == (SaveStatus.SAVED, None)

    autosave.changed(200.0)
    autosave.started()
    autosave.failed(201.0, "Disk full")

    assert autosave.deadline == 202.0
