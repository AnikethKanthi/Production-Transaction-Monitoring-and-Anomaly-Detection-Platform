from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import Settings
from app.db.base import Base
from app.models import InferenceFeature, ProcessedEvent, Transaction  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=Settings().sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif (connection := config.attributes.get("connection")) is not None:
    run_migrations(connection)
else:
    engine = create_engine(
        Settings().sqlalchemy_url, poolclass=pool.NullPool, connect_args={"connect_timeout": 10}
    )
    try:
        with engine.connect() as connection:
            run_migrations(connection)
    finally:
        engine.dispose()
