from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.dependencies import AlertServiceDependency
from app.schemas.alert import (
    AlertAssignment,
    AlertAuditRead,
    AlertDetails,
    AlertList,
    AlertMutation,
    AlertRead,
    AlertSeverity,
    AlertStatus,
)
from app.schemas.transaction import PaginationMeta

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    responses={
        404: {"description": "Alert not found"},
        409: {"description": "Stale version or invalid workflow transition"},
    },
)


@router.get("", response_model=AlertList)
def list_alerts(
    service: AlertServiceDependency,
    status: AlertStatus | None = None,
    severity: AlertSeverity | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AlertList:
    items, total = service.repository.list(status, severity, limit, offset)
    return AlertList(
        items=[AlertRead.model_validate(item) for item in items],
        pagination=PaginationMeta(limit=limit, offset=offset, total=total),
    )


@router.get("/{alert_id}", response_model=AlertDetails)
def alert_details(alert_id: UUID, service: AlertServiceDependency) -> AlertDetails:
    alert = service.get(alert_id)
    return AlertDetails(
        **AlertRead.model_validate(alert).model_dump(),
        audit_history=[
            AlertAuditRead.model_validate(item) for item in service.repository.audit(alert_id)
        ],
    )


@router.get("/{alert_id}/audit", response_model=list[AlertAuditRead])
def alert_audit(alert_id: UUID, service: AlertServiceDependency) -> list[AlertAuditRead]:
    service.get(alert_id)
    return [AlertAuditRead.model_validate(item) for item in service.repository.audit(alert_id)]


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge(alert_id: UUID, payload: AlertMutation, service: AlertServiceDependency):
    return service.mutate(alert_id, "acknowledge", payload)


@router.post("/{alert_id}/assign", response_model=AlertRead)
def assign(alert_id: UUID, payload: AlertAssignment, service: AlertServiceDependency):
    return service.mutate(alert_id, "assign", payload)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
def resolve(alert_id: UUID, payload: AlertMutation, service: AlertServiceDependency):
    return service.mutate(alert_id, "resolve", payload)


@router.post("/{alert_id}/false-positive", response_model=AlertRead)
def false_positive(alert_id: UUID, payload: AlertMutation, service: AlertServiceDependency):
    return service.mutate(alert_id, "false-positive", payload)
