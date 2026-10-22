"""When to save: the autosave state machine. See docs/SPEC.md §8 "Autosave".

Pure and clock-free: callers pass the current time in seconds from any monotonic
clock and run the saves themselves. `persistence.autosaver` drives it with a Qt
timer.
"""

from enum import StrEnum

DEBOUNCE = 0.75
"""Seconds after the last committed change before a save starts."""

RETRY_DELAYS = (1.0, 2.0, 5.0, 10.0)
"""Seconds before retrying after the 1st, 2nd, 3rd and every later failed save."""


class SaveStatus(StrEnum):
    SAVED = "saved"  # everything is on disk
    PENDING = "pending"  # changes are waiting out the debounce
    SAVING = "saving"
    FAILED = "failed"  # the last save failed and a retry is scheduled


def retry_delay(failures: int) -> float:
    """Seconds to wait after `failures` (at least 1) failed saves in a row."""
    return RETRY_DELAYS[min(failures, len(RETRY_DELAYS)) - 1]


class Autosave:
    """Tracks unsaved changes and decides when the next save should start.

    Only one save runs at a time: changes made while saving are picked up by
    another save once it finishes.
    """

    def __init__(self) -> None:
        self.status = SaveStatus.SAVED
        self.error: str | None = None  # why the last save failed, while failing
        self.deadline: float | None = None  # when the next save should start
        self._dirty = False  # changes that no finished or running save covers
        self._last_change = 0.0  # pragma: no mutate (read only after changed() sets it)
        self._failures = 0

    @property
    def unsaved(self) -> bool:
        """True while some committed change isn't on disk yet."""
        # pragma below: "saving" sorts after the other statuses, so `>=` is equivalent.
        return self._dirty or self.status is SaveStatus.SAVING  # pragma: no mutate

    def due(self, now: float) -> bool:
        return self.deadline is not None and now >= self.deadline

    def changed(self, now: float) -> None:
        """A change was committed to the document."""
        self._dirty = True
        self._last_change = now
        # While saving, the end of the save schedules the next one. While failing,
        # the retry schedule stands, so a failing disk isn't hit on every edit.
        if self.status in (SaveStatus.SAVED, SaveStatus.PENDING):
            self.status = SaveStatus.PENDING
            self.deadline = now + DEBOUNCE

    def started(self) -> None:
        """A save of the current document has started."""
        self.status = SaveStatus.SAVING
        self.deadline = None
        self._dirty = False

    def succeeded(self, now: float) -> None:
        self._failures = 0
        self.error = None
        if self._dirty:
            self.status = SaveStatus.PENDING
            self.deadline = max(now, self._last_change + DEBOUNCE)
        else:
            self.status = SaveStatus.SAVED

    def failed(self, now: float, reason: str) -> None:
        self._dirty = True
        self._failures += 1
        self.error = reason
        self.status = SaveStatus.FAILED
        self.deadline = now + retry_delay(self._failures)
