"""Conservative rate limiting and retry/backoff — shared by every source so
"how do we behave towards a source's servers" is defined in exactly one
place, not reimplemented per source.

Deliberately simple (a per-source last-call timestamp, not a token
bucket/leaky bucket) because the goal here is "never hammer a source," not
maximum throughput — see ``ScraperConfig`` docstring.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Callable, Tuple, TypeVar

logger = logging.getLogger("scraper")

T = TypeVar("T")


class RateLimiter:
    """Enforces a minimum interval between successive calls for the same
    key (typically a source name), plus optional random jitter so requests
    don't land in a suspiciously regular pattern. Thread-safe."""

    def __init__(self, min_interval_seconds: float, jitter_seconds: Tuple[float, float] = (0.0, 0.0)) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.jitter_seconds = jitter_seconds
        self._lock = threading.Lock()
        self._last_call_at: float = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call_at
            delay = max(0.0, self.min_interval_seconds - elapsed)
            jitter = random.uniform(*self.jitter_seconds) if self.jitter_seconds[1] > 0 else 0.0
            total_delay = delay + jitter
            if total_delay > 0:
                time.sleep(total_delay)
            self._last_call_at = time.monotonic()


class RetryExhaustedError(Exception):
    """Raised when ``retry_with_backoff`` exhausts every attempt. Carries
    the last underlying exception as ``__cause__``."""


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_retries: int,
    backoff_base_seconds: float,
    backoff_max_seconds: float,
    retryable_exceptions: Tuple[type, ...] = (Exception,),
    source_name: str = "",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn()``, retrying on any of ``retryable_exceptions`` with
    exponential backoff (``backoff_base_seconds * 2**attempt``, capped at
    ``backoff_max_seconds``). Never retries more than ``max_retries`` times
    total. Re-raises the last exception (wrapped in
    ``RetryExhaustedError``) if every attempt fails."""
    attempt = 0
    while True:
        try:
            return fn()
        except retryable_exceptions as exc:
            attempt += 1
            if attempt > max_retries:
                logger.warning("[WARN] %s: retries exhausted after %d attempts (%s)", source_name, attempt, exc)
                raise RetryExhaustedError(f"{source_name}: retries exhausted after {attempt} attempts") from exc
            delay = min(backoff_max_seconds, backoff_base_seconds * (2 ** (attempt - 1)))
            logger.info("[INFO] %s: attempt %d failed (%s), retrying in %.1fs", source_name, attempt, exc, delay)
            sleep(delay)
