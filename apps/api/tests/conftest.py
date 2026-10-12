import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import make_url

from alembic import command


@pytest.fixture
def database_connection() -> Iterator[Connection]:
    """Use an isolated schema; never upgrade/downgrade an existing app schema."""
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL must point to PostgreSQL")
    engine = create_engine(
        url.set(drivername="postgresql+psycopg"), connect_args={"connect_timeout": 5}
    )
    schema = f"test_monitoring_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            connection.commit()
            # Alembic reflection must compare the isolated schema, not public.
            connection.dialect.default_schema_name = schema
            try:
                yield connection
            finally:
                connection.rollback()
                connection.exec_driver_sql("SET search_path TO public")
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
                connection.commit()
    finally:
        engine.dispose()


@pytest.fixture
def alembic_config(database_connection: Connection) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = database_connection
    return config


@pytest.fixture
def migrated_connection(alembic_config: Config, database_connection: Connection) -> Connection:
    command.upgrade(alembic_config, "head")
    return database_connection
