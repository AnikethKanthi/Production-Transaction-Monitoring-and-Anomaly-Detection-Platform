import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from app.core.redaction import redact

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "service": "api",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", request_id.get()),
        }
        for name in (
            "transaction_id",
            "event_id",
            "route",
            "method",
            "status_code",
            "duration_seconds",
        ):
            if hasattr(record, name):
                entry[name] = getattr(record, name)
        if record.exc_info:
            entry["exception"] = type(record.exc_info[1]).__name__
        return json.dumps(redact(entry), default=str, allow_nan=False)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # Access logs contain raw URLs/query strings. Application telemetry logs route templates.
    for name in ("uvicorn.access", "httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = [logging.NullHandler()]
        logging.getLogger(name).propagate = False
