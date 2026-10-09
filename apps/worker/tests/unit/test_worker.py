from threading import Event, Thread

import pytest
from pydantic import ValidationError

from worker.config import Settings
from worker.main import run


def test_worker_stops_when_signalled() -> None:
    stop = Event()
    thread = Thread(target=run, args=(stop, Settings(worker_heartbeat_seconds=0.01)))
    thread.start()
    stop.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_heartbeat_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(worker_heartbeat_seconds=0)
