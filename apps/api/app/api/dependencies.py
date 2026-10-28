from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.repositories.alerts import AlertRepository
from app.db.repositories.metrics import MetricsRepository
from app.db.repositories.transactions import TransactionRepository
from app.db.session import get_session
from app.services.alert_service import AlertService
from app.services.metrics_service import MetricsCache, MetricsService
from app.services.rolling_metrics import RollingMetricsService
from app.services.transaction_service import TransactionService

DatabaseSession = Annotated[Session, Depends(get_session, scope="function")]


def get_alert_service(session: DatabaseSession) -> AlertService:
    return AlertService(AlertRepository(session))


AlertServiceDependency = Annotated[AlertService, Depends(get_alert_service)]


def get_transaction_service(session: DatabaseSession) -> TransactionService:
    return TransactionService(TransactionRepository(session))


TransactionServiceDependency = Annotated[TransactionService, Depends(get_transaction_service)]


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(Settings().redis_url, decode_responses=True)


def get_metrics_service(session: DatabaseSession) -> MetricsService:
    settings = Settings()
    return MetricsService(
        MetricsRepository(session), MetricsCache(get_redis(), settings.metrics_cache_ttl_seconds)
    )


MetricsServiceDependency = Annotated[MetricsService, Depends(get_metrics_service)]


def get_rolling_metrics_service() -> RollingMetricsService:
    return RollingMetricsService(get_redis())


RollingMetricsServiceDependency = Annotated[
    RollingMetricsService, Depends(get_rolling_metrics_service)
]
