"""Runs the autosave state machine on a Qt timer."""

import logging
import math
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from apartment_planner.persistence.autosave import Autosave, SaveStatus
from apartment_planner.persistence.errors import ProjectFileError, describe_os_error

log = logging.getLogger(__name__)


def describe_save_error(error: Exception) -> str:
    if isinstance(error, OSError):
        return describe_os_error(error)
    if isinstance(error, ProjectFileError):
        return str(error)
    return f"Unexpected error: {error!r}"


class Autosaver(QObject):
    """Calls `save` when the state machine says so, and reports the outcome.

    Saves run synchronously on the GUI thread; `save` raises on failure. The
    in-memory document is untouched by a failure, so nothing is lost while
    retrying.
    """

    status_changed = Signal()

    def __init__(
        self,
        save: Callable[[], None],
        *,
        clock: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._save = save
        self._clock = clock
        self._machine = Autosave()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    @property
    def status(self) -> SaveStatus:
        return self._machine.status

    @property
    def error(self) -> str | None:
        return self._machine.error

    @property
    def unsaved(self) -> bool:
        return self._machine.unsaved

    def changed(self) -> None:
        """Call after every committed change to the document."""
        self._machine.changed(self._clock())
        self._arm_timer()
        self.status_changed.emit()

    def flush(self) -> bool:
        """Save now if anything is unsaved. True when everything is on disk."""
        if self._machine.unsaved:
            self._run_save()
        return not self._machine.unsaved

    def stop(self) -> None:
        self._timer.stop()

    def _on_timeout(self) -> None:
        if self._machine.due(self._clock()):
            self._run_save()
        else:
            self._arm_timer()

    def _run_save(self) -> None:
        self._machine.started()
        self.status_changed.emit()
        try:
            self._save()
        except Exception as error:  # reported in the status bar and retried
            log.warning("Save failed", exc_info=True)
            self._machine.failed(self._clock(), describe_save_error(error))
        else:
            self._machine.succeeded(self._clock())
        self._arm_timer()
        self.status_changed.emit()

    def _arm_timer(self) -> None:
        deadline = self._machine.deadline
        if deadline is None:
            self._timer.stop()
        else:
            self._timer.start(max(0, math.ceil((deadline - self._clock()) * 1000)))
