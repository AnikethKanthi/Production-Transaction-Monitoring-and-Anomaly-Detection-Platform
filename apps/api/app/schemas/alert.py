from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.transaction import PaginationMeta

Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class AlertStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    false_positive = "false_positive"


class AlertSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AlertMutation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"expected_version": 1, "actor": "analyst-17", "reason": "Starting investigation"}
            ]
        },
    )

    expected_version: int = Field(ge=1, strict=True)
    actor: Nonempty
    reason: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class AlertAssignment(AlertMutation):
    assignee: Nonempty


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    anomaly_id: UUID
    event_id: UUID
    severity: AlertSeverity
    policy_version: str
    model_version: str
    evidence: dict
    status: AlertStatus
    assignee: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class AlertAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alert_id: UUID
    version: int
    action: str
    actor: str
    reason: str
    before: dict | None
    after: dict
    created_at: datetime


class AlertDetails(AlertRead):
    audit_history: list[AlertAuditRead]


class AlertList(BaseModel):
    items: list[AlertRead]
    pagination: PaginationMeta
