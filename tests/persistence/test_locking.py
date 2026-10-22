import os
import time
from pathlib import Path

import pytest

from apartment_planner.persistence.locking import (
    LockUnavailableError,
    ProjectLock,
    ProjectLockedError,
    describe_holder,
    lock_path,
)


def test_lock_is_exclusive_until_released(tmp_path: Path) -> None:
    path = tmp_path / "Flat.apartment"
    first, second = ProjectLock(path), ProjectLock(path)

    first.acquire()
    with pytest.raises(ProjectLockedError, match="this computer in another"):
        second.acquire()
    first.release()
    second.acquire()
    second.release()

    assert not lock_path(path).exists()


def test_lock_held_on_another_computer_never_goes_stale(tmp_path: Path) -> None:
    path = tmp_path / "Flat.apartment"
    lock_path(path).write_bytes(b"4242\napartment-planner\nROGER-PC\n")  # PID, app, host
    an_hour_ago = time.time() - 3600
    os.utime(lock_path(path), (an_hour_ago, an_hour_ago))

    with pytest.raises(ProjectLockedError, match='"Flat" is open on "ROGER-PC"'):
        ProjectLock(path).acquire()


def test_lock_that_cannot_be_created_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(LockUnavailableError, match="folder"):
        ProjectLock(tmp_path / "missing folder" / "Flat.apartment").acquire()


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("my-laptop", "this computer in another Apartment Planner window"),
        ("ROGER-PC", '"ROGER-PC"'),
        ("", "another computer"),
    ],
)
def test_describe_holder(host: str, expected: str) -> None:
    assert describe_holder(host, this_host="my-laptop") == expected
