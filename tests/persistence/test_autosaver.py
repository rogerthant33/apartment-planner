from pytestqt.qtbot import QtBot

from apartment_planner.persistence.autosave import SaveStatus
from apartment_planner.persistence.autosaver import Autosaver


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def deny() -> None:
    raise PermissionError(13, "Access is denied")


def test_saves_when_the_debounce_timer_fires(qtbot: QtBot) -> None:
    clock = FakeClock()
    saves: list[float] = []
    autosaver = Autosaver(lambda: saves.append(clock.now), clock=clock)

    autosaver.changed()
    assert autosaver._timer.interval() == 750
    clock.now = 0.75
    with qtbot.waitSignal(autosaver.status_changed):
        autosaver._timer.timeout.emit()

    assert saves == [0.75]
    assert autosaver.status is SaveStatus.SAVED


def test_failed_save_is_reported_and_retried(qtbot: QtBot) -> None:
    autosaver = Autosaver(deny, clock=FakeClock())
    autosaver.changed()

    assert not autosaver.flush()
    assert autosaver.status is SaveStatus.FAILED
    assert autosaver.error == "Access is denied"
    assert autosaver._timer.isActive()
    assert autosaver._timer.interval() == 1000


def test_flush_saves_at_once_and_only_when_needed(qtbot: QtBot) -> None:
    saves: list[float] = []
    autosaver = Autosaver(lambda: saves.append(1), clock=FakeClock())
    assert autosaver.flush()
    assert saves == []

    autosaver.changed()
    assert autosaver.flush()

    assert saves == [1]
    assert not autosaver._timer.isActive()
