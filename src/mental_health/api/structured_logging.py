"""Small JSON event logger for operator-visible API failures."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone


EVENT_LOGGER_NAME = "mental_health.api.events"
EVENT_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "exception_type",
    "traceback",
)


class JsonEventFormatter(logging.Formatter):
    """Render one application event as one JSON line on server stderr."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "application_log"),
            "message": record.getMessage(),
        }
        for field in EVENT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, allow_nan=False, ensure_ascii=True, sort_keys=True)


def configure_event_logger() -> logging.Logger:
    """Attach one JSON stderr handler without duplicating handlers on reloads."""
    event_logger = logging.getLogger(EVENT_LOGGER_NAME)
    if not any(
        getattr(handler, "_mental_health_json_event_handler", False)
        for handler in event_logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonEventFormatter())
        handler._mental_health_json_event_handler = True  # type: ignore[attr-defined]
        event_logger.addHandler(handler)
    event_logger.setLevel(logging.INFO)
    event_logger.propagate = False
    return event_logger


event_logger = configure_event_logger()


def log_unhandled_request_exception(
    *,
    request_id: str,
    method: str,
    path: str,
    exc: Exception,
) -> None:
    """Record the internal failure while the client receives a generic 500."""
    traceback_text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    event_logger.error(
        "Unhandled request exception",
        extra={
            "event": "unhandled_exception",
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": 500,
            "exception_type": type(exc).__name__,
            "traceback": traceback_text,
        },
    )
