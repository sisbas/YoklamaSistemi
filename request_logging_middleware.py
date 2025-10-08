"""Request/response logging middleware for Flask."""

from __future__ import annotations

import json
import os
import random
import time
from typing import Any, Dict

from flask import Flask, Response, g, request

from app_logging import get_logger, merge_request_context, redact_sensitive_data
from correlation_id_middleware import HEADER_NAME

_DEFAULT_SAMPLE_RATE = 1.0
_DEFAULT_MAX_BYTES = 2048

_request_logger = get_logger("app.request")


def _sample_rate() -> float:
    try:
        return max(0.0, min(1.0, float(os.environ.get("REQUEST_LOG_SAMPLE_RATE", _DEFAULT_SAMPLE_RATE))))
    except ValueError:
        return _DEFAULT_SAMPLE_RATE


def _max_response_bytes() -> int:
    try:
        return max(0, int(os.environ.get("RESPONSE_BODY_MAX_BYTES", _DEFAULT_MAX_BYTES)))
    except ValueError:
        return _DEFAULT_MAX_BYTES


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _should_skip(path: str) -> bool:
    return path.startswith("/static") or path.startswith("/_static") or path in {"/health"}


def _should_log_request(path: str) -> bool:
    if _should_skip(path):
        return False
    sample_rate = _sample_rate()
    if sample_rate >= 1.0:
        return True
    return random.random() <= sample_rate


def _extract_request_payload() -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    try:
        if request.args:
            payload["query"] = redact_sensitive_data(request.args.to_dict(flat=False))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            json_body = request.get_json(silent=True)
            if json_body is not None:
                payload["json"] = redact_sensitive_data(json_body)
    except Exception:
        payload["body_error"] = "unavailable"
    return payload


def _truncate_response_body(resp: Response) -> str | None:
    if resp.direct_passthrough:
        return None
    try:
        body = resp.get_data(as_text=True)
    except Exception:
        return None
    if body and resp.mimetype and 'json' in resp.mimetype:
        try:
            json_body = json.loads(body)
            body = json.dumps(redact_sensitive_data(json_body))
        except Exception:
            pass
    limit = _max_response_bytes()
    if limit == 0 or body is None:
        return None
    if len(body) > limit:
        truncated = body[:limit] + f"... truncated {len(body) - limit} bytes"
        return truncated
    return body


def init_request_logging(app: Flask) -> None:
    """Register Flask hooks that emit structured request/response logs."""

    @app.before_request
    def _log_request_start() -> None:
        should_log = _should_log_request(request.path)
        g._log_request = should_log
        g._request_start = time.perf_counter()
        merge_request_context(
            method=request.method,
            path=request.path,
            client_ip=_client_ip(),
            user_agent=request.headers.get("User-Agent"),
            route=request.url_rule.rule if request.url_rule else None,
        )
        if not should_log:
            return
        payload = _extract_request_payload()
        _request_logger.info(
            "request_start",
            extra={
                "event": "request_start",
                "method": request.method,
                "path": request.path,
                "client_ip": _client_ip(),
                "user_agent": request.headers.get("User-Agent"),
                "route": request.url_rule.rule if request.url_rule else None,
                "request_payload": payload,
            },
        )

    @app.after_request
    def _log_request_end(response: Response) -> Response:
        merge_request_context(status=response.status_code)
        duration_ms = None
        if hasattr(g, "_request_start"):
            duration_ms = (time.perf_counter() - g._request_start) * 1000
            merge_request_context(duration_ms=round(duration_ms, 2))
        if getattr(g, "_log_request", False):
            response_body = _truncate_response_body(response)
            extra = {
                "event": "request_end",
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
                "route": request.url_rule.rule if request.url_rule else None,
                "response_body": response_body,
                "response_headers": {
                    k: v for k, v in response.headers.items() if k.lower() not in {"set-cookie"}
                },
            }
            _request_logger.info("request_end", extra=extra)
        response.headers.setdefault(HEADER_NAME, getattr(g, "request_id", ""))
        return response


__all__ = ["init_request_logging"]
