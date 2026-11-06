from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


@lru_cache
def get_engine() -> Engine:
    """Create a process-local pool lazily; API liveness needs no database connection."""
    settings = Settings()
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_recycle=settings.database_pool_recycle_seconds,
        pool_use_lifo=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.database_connect_timeout_seconds,
            "options": (
                f"-c statement_timeout={settings.database_statement_timeout_ms} "
                "-c lock_timeout=2000"
            ),
        },
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Yield one unit of work; commit on success, rollback on error, always close.

    In FastAPI routes use Depends(get_session, scope="function") so the commit
    completes before a success response is sent. Do not share sessions across threads.
    """
    with get_session_factory().begin() as session:
        yield session
