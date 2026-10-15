from threading import Event, Thread
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from worker.config import Settings
from worker.main import run
from worker.persistence.database import get_session_factory


def test_worker_stops_when_signalled() -> None:
    stop = Event()
    consumer = Mock()
    consumer.run.side_effect = lambda event: event.wait(1)
    thread = Thread(target=run, args=(stop, Settings(), consumer))
    thread.start()
    stop.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_poll_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(kafka_poll_timeout_seconds=0)


def test_processing_attempts_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(kafka_max_processing_attempts=0)


def test_session_factory_accepts_settings() -> None:
    factory = get_session_factory(Settings())
    try:
        assert factory.kw["expire_on_commit"] is False
    finally:
        factory.kw["bind"].dispose()
