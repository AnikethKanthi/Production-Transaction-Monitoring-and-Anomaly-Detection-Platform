from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "127.0.0.1:9092"
    kafka_consumer_group: str = "transaction-processor-v1"
    kafka_poll_timeout_seconds: float = Field(default=1, gt=0, le=30)
