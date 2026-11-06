from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from worker.config import Settings


def get_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = create_engine(
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
    return sessionmaker(engine, expire_on_commit=False)
