from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


@lru_cache
def get_engine() -> Engine:
    """Create a process-local pool lazily; API liveness needs no database connection."""
    return create_engine(
        Settings().sqlalchemy_url, pool_pre_ping=True, connect_args={"connect_timeout": 10}
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
