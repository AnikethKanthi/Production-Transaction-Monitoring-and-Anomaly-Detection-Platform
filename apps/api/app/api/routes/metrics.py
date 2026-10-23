from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import MetricsServiceDependency, RollingMetricsServiceDependency
from app.schemas.metrics import MetricsResponse, RollingMetricsResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
def dashboard_metrics(
    service: MetricsServiceDependency,
    start: Annotated[datetime, Query(description="Inclusive range start with timezone")],
    end: Annotated[datetime, Query(description="Exclusive range end with timezone")],
    interval: Literal["hour", "day"] = "hour",
    currency: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
) -> MetricsResponse:
    try:
        return service.dashboard(start, end, interval, currency)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/rolling", response_model=RollingMetricsResponse)
def rolling_metrics(
    service: RollingMetricsServiceDependency,
    window_minutes: Annotated[int, Query(ge=1, le=120)] = 60,
) -> RollingMetricsResponse:
    return service.dashboard(window_minutes)
