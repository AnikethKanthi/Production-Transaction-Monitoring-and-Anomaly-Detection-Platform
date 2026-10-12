from pydantic import SecretStr

from app.core.config import Settings


def test_database_url_safely_encodes_password() -> None:
    settings = Settings(
        _env_file=None, database_url=None, postgres_password=SecretStr("p@ss:%/word")
    )
    url = settings.sqlalchemy_url
    assert url.password == "p@ss:%/word"
    assert "p@ss" not in str(url)
    assert url.drivername == "postgresql+psycopg"


def test_explicit_database_url_takes_precedence() -> None:
    settings = Settings(
        _env_file=None,
        database_url=SecretStr("postgresql://client:secret@db.example:5433/other"),
    )
    assert settings.sqlalchemy_url.host == "db.example"
    assert settings.sqlalchemy_url.database == "other"
    assert settings.sqlalchemy_url.drivername == "postgresql+psycopg"
