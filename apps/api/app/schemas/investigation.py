from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.alert import AlertRead
from app.schemas.transaction import TransactionRead


class AnomalyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    score: float
    model_version: str
    scoring_status: str
    failure_reason: str | None
    inference_latency_seconds: float
    created_at: datetime


class TransactionInvestigation(BaseModel):
    transaction: TransactionRead
    anomaly: AnomalyRead | None
    alerts: list[AlertRead]
