from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Transaction Monitoring API"
    database_url: SecretStr | None = None
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "transactions"
    postgres_user: str = "monitoring"
    postgres_password: SecretStr = SecretStr("local-development-only")

    @property
    def sqlalchemy_url(self) -> URL:
        if self.database_url is not None:
            url = make_url(self.database_url.get_secret_value())
            if url.drivername not in {"postgresql", "postgresql+psycopg"}:
                raise ValueError("DATABASE_URL must use PostgreSQL with the psycopg driver")
            return url.set(drivername="postgresql+psycopg")
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
