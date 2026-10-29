from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.router import router
from app.core.config import Settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.telemetry import TelemetryMiddleware

settings = Settings()
configure_logging()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(TelemetryMiddleware)
register_exception_handlers(app)
app.include_router(router)


@app.get("/metrics/prometheus", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(generate_latest(), headers={"content-type": CONTENT_TYPE_LATEST})
