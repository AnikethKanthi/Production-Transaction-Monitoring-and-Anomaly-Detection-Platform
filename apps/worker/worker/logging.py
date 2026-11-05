import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from worker.redaction import redact

log_context: ContextVar[dict] = ContextVar("worker_log_context", default={})


@contextmanager
def event_context(event):
    token = log_context.set(
        {
            "correlation_id": event.correlation_id or str(event.event_id),
            "event_id": str(event.event_id),
            "transaction_id": str(event.data.transaction_id),
        }
    )
    try:
        yield
    finally:
        log_context.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "service": "worker",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **log_context.get(),
        }
        for name in (
            "correlation_id",
            "event_id",
            "transaction_id",
            "topic",
            "partition",
            "offset",
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
    for name in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = [logging.NullHandler()]
        logging.getLogger(name).propagate = False
