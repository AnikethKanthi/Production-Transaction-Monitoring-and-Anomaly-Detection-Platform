from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "127.0.0.1:9092"
    kafka_consumer_group: str = "transaction-processor-v1"
    kafka_poll_timeout_seconds: float = Field(default=1, gt=0, le=30)
    kafka_max_processing_attempts: int = Field(default=3, ge=1, le=10)
    kafka_retry_backoff_seconds: float = Field(default=0.5, ge=0, le=60)
    model_path: Path = Path("model-artifacts/isolation_forest.v1.joblib")
    model_metadata_path: Path = Path("model-artifacts/isolation_forest.v1.metadata.json")
    metrics_port: int = Field(default=9101, ge=1, le=65535)
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
