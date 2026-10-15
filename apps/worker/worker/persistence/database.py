from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from worker.config import Settings


def get_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    return sessionmaker(engine, expire_on_commit=False)
