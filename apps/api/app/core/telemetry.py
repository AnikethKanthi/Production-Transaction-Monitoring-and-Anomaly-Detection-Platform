import logging
import re
import time
from uuid import uuid4

from prometheus_client import Counter, Histogram

from app.core.logging import request_id

logger = logging.getLogger(__name__)
REQUESTS = Counter(
    "api_http_requests_total",
    "Completed API requests, including errors.",
    ("method", "route", "status_code"),
)
LATENCY = Histogram(
    "api_http_request_duration_seconds",
    "API response latency in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)


class TelemetryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"x-correlation-id", b"").decode("ascii", errors="ignore")
        correlation = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied) else uuid4().hex
        token = request_id.set(correlation)
        status_code = 500
        started = time.perf_counter()

        async def wrapped_send(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message = dict(message)
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-correlation-id"
                ] + [(b"x-correlation-id", correlation.encode("ascii"))]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            logger.exception("Unhandled API request failure")
            raise
        finally:
            elapsed = time.perf_counter() - started
            route = getattr(scope.get("route"), "path", "unmatched")
            method = (
                scope["method"]
                if scope["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                else "OTHER"
            )
            if route != "/metrics/prometheus":
                REQUESTS.labels(method, route, str(status_code)).inc()
                LATENCY.labels(method, route).observe(elapsed)
                logger.info(
                    "API request completed",
                    extra={
                        "route": route,
                        "method": method,
                        "status_code": status_code,
                        "duration_seconds": elapsed,
                    },
                )
            request_id.reset(token)
