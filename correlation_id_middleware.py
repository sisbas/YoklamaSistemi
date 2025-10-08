"""Correlation ID middleware for Flask applications."""

from __future__ import annotations

import uuid
from typing import Optional

from flask import Flask, g, request

from app_logging import clear_request_context, clear_request_id, merge_request_context, set_request_id

HEADER_NAME = "X-Request-ID"


def _incoming_request_id() -> Optional[str]:
    header_val = request.headers.get(HEADER_NAME, "").strip()
    return header_val or None


def init_correlation_id(app: Flask) -> None:
    """Register handlers that attach a correlation ID to each request."""

    @app.before_request
    def _assign_request_id() -> None:
        request_id = _incoming_request_id() or str(uuid.uuid4())
        set_request_id(request_id)
        merge_request_context(request_id=request_id)
        g.request_id = request_id

    @app.after_request
    def _append_request_id(response):
        request_id = getattr(g, "request_id", None) or _incoming_request_id()
        if request_id:
            response.headers[HEADER_NAME] = request_id
        return response

    @app.teardown_request
    def _teardown_request(_exc):
        clear_request_id()
        clear_request_context()


__all__ = ["init_correlation_id", "HEADER_NAME"]
