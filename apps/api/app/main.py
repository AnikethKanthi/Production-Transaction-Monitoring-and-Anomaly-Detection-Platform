from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.router import router
from app.core.business_metrics import snapshot
from app.core.config import Settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_protection import RequestProtectionMiddleware
from app.core.telemetry import TelemetryMiddleware

configure_logging()
settings = Settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(TelemetryMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID", "Retry-After"],
)
app.add_middleware(
    RequestProtectionMiddleware,
    max_bytes=settings.max_request_bytes,
    body_timeout=settings.request_body_timeout_seconds,
)
register_exception_handlers(app)
app.include_router(router)


@app.get("/metrics/prometheus", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(generate_latest(), headers={"content-type": CONTENT_TYPE_LATEST})


@app.get("/metrics/business", include_in_schema=False)
def business_metrics() -> Response:
    return Response(snapshot(), headers={"content-type": CONTENT_TYPE_LATEST})
