"""Structured JSON logging setup for the backend's own operational logs."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Set by the request-ID middleware (see main.py) for the duration of a
# request, so every log line emitted while handling it can be tied back to
# that request. Unset for background jobs (aggregator, retention, etc.) --
# there's no request to correlate those with, which is correct.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in ("message", "asctime") or key in logging.LogRecord.__dict__:
                continue
            if key.startswith("_"):
                continue
            if key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Quiet noisy third-party loggers at DEBUG unless explicitly raised.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
