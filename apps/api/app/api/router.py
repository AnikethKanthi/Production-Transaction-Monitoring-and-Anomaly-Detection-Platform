from fastapi import APIRouter, Depends

from app.api.routes.alerts import router as alerts_router
from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.transactions import router as transactions_router
from app.core.security import Authenticated, get_principal

router = APIRouter()
router.include_router(health_router)
router.include_router(transactions_router, dependencies=[Depends(get_principal)])
router.include_router(metrics_router, dependencies=[Depends(get_principal)])
router.include_router(alerts_router, dependencies=[Depends(get_principal)])


@router.get("/auth/me", tags=["authentication"])
def current_user(principal: Authenticated):
    return principal
