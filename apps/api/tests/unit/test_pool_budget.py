import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError
from sqlalchemy.pool import QueuePool

from app.core.config import Settings


def test_api_pool_budget_is_bounded_and_exhaustion_times_out():
    settings = Settings(
        _env_file=None,
        database_pool_size=1,
        database_max_overflow=0,
        database_pool_timeout_seconds=0.01,
    )
    engine = create_engine(
        "sqlite://",
        poolclass=QueuePool,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
    )
    try:
        with engine.connect():
            with pytest.raises(TimeoutError):
                engine.connect()
    finally:
        engine.dispose()
    with pytest.raises(ValueError):
        Settings(_env_file=None, database_max_overflow=-1)
