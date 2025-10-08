"""Database resilience helpers."""

from __future__ import annotations

import time
from typing import Callable, TypeVar

from app_logging import get_logger

T = TypeVar("T")

_logger = get_logger("app.db")


def retry_with_backoff(
    func: Callable[[], T],
    attempts: int = 3,
    base_delay: float = 0.1,
    max_total_delay: float = 2.0,
) -> T:
    """Retry ``func`` with exponential backoff.

    The helper is intentionally simple and synchronous. It avoids exceeding the
    configured ``max_total_delay`` to keep application start-up fast.
    """

    last_exc: Exception | None = None
    total_delay = 0.0
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - behaviour validated via logs
            last_exc = exc
            _logger.warning(
                "transient operation failed", extra={"attempt": attempt, "error": str(exc)}
            )
            if attempt >= attempts or total_delay >= max_total_delay:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_total_delay - total_delay)
            if delay <= 0:
                continue
            time.sleep(delay)
            total_delay += delay
    if last_exc:
        raise last_exc
    raise RuntimeError("retry_with_backoff failed without exception")


__all__ = ["retry_with_backoff"]
