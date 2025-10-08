"""Centralised JSON logging configuration and helpers.

This module configures the standard library ``logging`` package to emit
single-line JSON records that can easily be ingested by log aggregators. It
also exposes convenience helpers for working with per-request context such as
correlation IDs. The implementation intentionally avoids heavy third-party
dependencies so it works well in constrained environments like Heroku dynos.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib import request as urlrequest

# ---------------------------------------------------------------------------
# Context management
# ---------------------------------------------------------------------------

_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
_request_context_ctx: contextvars.ContextVar[Optional[Dict[str, Any]]] = (
    contextvars.ContextVar("request_context", default=None)
)

_REDACTED = "[REDACTED]"
_SENSITIVE_FIELDS = {
    field.strip().lower()
    for field in os.environ.get("SENSITIVE_FIELDS", "password,token,email,phone").split(","
    )
    if field.strip()
}

_JSON_LOG_FIELDS = (
    "ts",
    "level",
    "logger",
    "msg",
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "client_ip",
    "user_agent",
    "route",
    "db_time_ms",
    "error_type",
    "error",
    "stack",
    "extra_context",
)


def get_request_id() -> Optional[str]:
    """Return the correlation ID for the current request, if any."""

    return _request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """Associate a correlation ID with the current context."""

    _request_id_ctx.set(request_id)
    merge_request_context(request_id=request_id)


def clear_request_id() -> None:
    """Clear the request ID for the current context."""

    _request_id_ctx.set(None)


def get_request_context() -> Dict[str, Any]:
    """Return contextual information about the current request."""

    ctx = _request_context_ctx.get()
    if ctx is None:
        ctx = {}
        _request_context_ctx.set(ctx)
    return ctx


def merge_request_context(**kwargs: Any) -> None:
    """Merge key/value pairs into the current request context."""

    ctx = dict(get_request_context())
    for key, value in kwargs.items():
        if value is not None:
            ctx[key] = value
    _request_context_ctx.set(ctx)


def clear_request_context() -> None:
    """Remove all contextual information for the current request."""

    _request_context_ctx.set({})


# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------

def sensitive_fields() -> Iterable[str]:
    """Return the set of case-insensitive sensitive field names."""

    return _SENSITIVE_FIELDS


def redact_sensitive_data(data: Any, fields: Optional[Iterable[str]] = None) -> Any:
    """Redact sensitive values from mappings or sequences.

    The function works recursively for nested dictionaries and lists. Scalars
    are returned unchanged. Keys are compared in a case-insensitive manner.
    """

    fields_set = {field.lower() for field in (fields or sensitive_fields())}

    if isinstance(data, Mapping):
        redacted: Dict[Any, Any] = {}
        for key, value in data.items():
            lowered = str(key).lower()
            if lowered in fields_set:
                redacted[key] = _REDACTED
            else:
                redacted[key] = redact_sensitive_data(value, fields_set)
        return redacted
    if isinstance(data, (list, tuple, set)):
        return [redact_sensitive_data(item, fields_set) for item in data]
    return data


# ---------------------------------------------------------------------------
# JSON logging infrastructure
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Formatter that renders log records as single-line JSON objects."""

    # Attributes populated by logging.LogRecord that we do not want to surface
    _RESERVED = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc)
        payload: Dict[str, Any] = {
            "ts": timestamp.isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": get_request_id(),
            "stack": None,
            "extra_context": None,
        }

        # Start from request-scoped context
        for key, value in get_request_context().items():
            if key not in payload or payload[key] is None:
                payload[key] = value

        # Include well-known attributes if present on the record
        for field in (
            "method",
            "path",
            "status",
            "duration_ms",
            "client_ip",
            "user_agent",
            "route",
            "db_time_ms",
            "error_type",
            "error",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        # Handle exceptions
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__
            payload["error"] = str(record.exc_info[1])
            payload["stack"] = self.formatException(record.exc_info)
        elif getattr(record, "stack_info", None):
            payload["stack"] = record.stack_info

        extra: Dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key in payload or key.startswith("_"):
                continue
            extra[key] = value

        if extra:
            payload["extra_context"] = redact_sensitive_data(extra)

        # Ensure every expected field exists for downstream consumers
        for field in _JSON_LOG_FIELDS:
            payload.setdefault(field, None)

        return json.dumps(payload, default=_json_default, separators=(",", ":"))


def _json_default(obj: Any) -> Any:
    """JSON serialiser fallback."""

    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    return str(obj)


class SlackWebhookHandler(logging.Handler):
    """Optional handler that posts error logs to a Slack incoming webhook."""

    def __init__(self, webhook_url: str, timeout: float = 2.0) -> None:
        super().__init__(level=logging.ERROR)
        self.webhook_url = webhook_url
        self.timeout = timeout
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = {
                "text": f"[{record.levelname}] {record.getMessage()} (request_id={get_request_id()})"
            }
            data = json.dumps(payload).encode("utf-8")
            req = urlrequest.Request(self.webhook_url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with self._lock:
                urlrequest.urlopen(req, timeout=self.timeout)
        except Exception:  # pragma: no cover - never break logging on failure
            self.handleError(record)


_configured = False


def configure_logging() -> None:
    """Configure root logging with a JSON formatter."""

    global _configured
    if _configured:
        return

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
    logging.captureWarnings(True)

    # Silence noisy third-party loggers; application middleware emits
    # request/response logs explicitly.
    for noisy_logger in (
        "gunicorn",
        "gunicorn.access",
        "gunicorn.error",
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
    ):
        log = logging.getLogger(noisy_logger)
        log.handlers = []
        log.propagate = True
        log.setLevel(logging.WARNING)

    webhook_url = os.environ.get("LOG_SLACK_WEBHOOK_URL")
    if webhook_url:
        root.addHandler(SlackWebhookHandler(webhook_url))

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger instance using the configured JSON formatter."""

    configure_logging()
    logger = logging.getLogger(name)
    return logger


# Convenience to track database timings via context manager
class DBTimer:
    """Simple helper to track database time and expose it in logs."""

    def __enter__(self) -> "DBTimer":  # pragma: no cover - trivial
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
        duration = (time.perf_counter() - getattr(self, "_start", time.perf_counter())) * 1000
        merge_request_context(db_time_ms=round(duration, 2))


__all__ = [
    "DBTimer",
    "clear_request_context",
    "clear_request_id",
    "configure_logging",
    "get_logger",
    "get_request_context",
    "get_request_id",
    "merge_request_context",
    "redact_sensitive_data",
    "sensitive_fields",
    "set_request_id",
]
