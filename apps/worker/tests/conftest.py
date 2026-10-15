import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from worker.persistence.models import Base


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL must point to PostgreSQL")
    engine = create_engine(
        url.set(drivername="postgresql+psycopg"), connect_args={"connect_timeout": 5}
    )
    schema = f"test_worker_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            connection.commit()
            Base.metadata.create_all(connection)
            connection.commit()
            try:
                yield sessionmaker(connection, expire_on_commit=False)
            finally:
                connection.rollback()
                connection.exec_driver_sql("SET search_path TO public")
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
                connection.commit()
    finally:
        engine.dispose()
