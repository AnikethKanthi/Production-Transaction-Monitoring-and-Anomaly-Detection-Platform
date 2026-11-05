from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from worker.config import Settings


def get_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_timeout=3,
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
