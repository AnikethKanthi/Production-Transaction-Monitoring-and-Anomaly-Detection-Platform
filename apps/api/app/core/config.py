from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class AuthUser(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    role: Literal["operator", "administrator"]
    token_sha256: str = Field(pattern=r"^[a-f0-9]{64}$", repr=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_name: str = "Transaction Monitoring API"
    auth_users: list[AuthUser] = Field(default_factory=list, repr=False)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    max_request_bytes: int = Field(default=65536, ge=1024, le=1048576)
    request_body_timeout_seconds: float = Field(default=5, gt=0, le=30)
    rate_limit_requests: int = Field(default=120, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    redis_timeout_seconds: float = Field(default=1, gt=0, le=5)
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=10)
    database_statement_timeout_ms: int = Field(default=5000, ge=100, le=30000)

    @model_validator(mode="after")
    def validate_security(self):
        if len({user.username for user in self.auth_users}) != len(self.auth_users):
            raise ValueError("Authentication usernames must be unique")
        if len({user.token_sha256 for user in self.auth_users}) != len(self.auth_users):
            raise ValueError("Authentication token hashes must be unique")
        if "*" in self.cors_origins:
            raise ValueError("Explicit CORS origins are required")
        return self

    database_url: SecretStr | None = None
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "transactions"
    postgres_user: str = "monitoring"
    postgres_password: SecretStr = SecretStr("local-development-only")
    redis_url: str = "redis://127.0.0.1:6379/0"
    metrics_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    rolling_metrics_ttl_seconds: int = Field(default=7200, ge=60, le=604800)

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
