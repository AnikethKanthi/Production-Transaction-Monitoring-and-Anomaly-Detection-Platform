from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "api"
    version: str = "0.1.0"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report API liveness; Compose checks infrastructure separately."""
    return HealthResponse()
