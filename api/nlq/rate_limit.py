"""Rate limiting and concurrency control for the NLQ endpoint.

Provides two FastAPI dependencies:
- require_rate_limit: per-IP sliding window rate limiter
- require_ollama_slot: asyncio.Semaphore limiting concurrent Ollama calls
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request

from config.settings import config

# ---------------------------------------------------------------------------
# Per-IP sliding window rate limiter
# ---------------------------------------------------------------------------


class SlidingWindowRateLimiter:
    """In-memory per-key sliding window rate limiter.

    Stores request timestamps per key (typically client IP). On each check,
    prunes timestamps outside the window and compares count to max_requests.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check whether a request from *key* is allowed.

        Returns:
            A tuple of (allowed, retry_after_seconds).
            retry_after_seconds is 0 when allowed is True.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Prune expired timestamps
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]

        if len(self._requests[key]) >= self.max_requests:
            oldest = self._requests[key][0]
            retry_after = int(oldest - cutoff) + 1
            return False, max(retry_after, 1)

        self._requests[key].append(now)
        return True, 0


# Module-level singletons (lazily created)
_rate_limiter: SlidingWindowRateLimiter | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_rate_limiter() -> SlidingWindowRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = SlidingWindowRateLimiter(
            max_requests=config.NLQ_RATE_LIMIT,
            window_seconds=config.NLQ_RATE_LIMIT_WINDOW,
        )
    return _rate_limiter


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.NLQ_MAX_CONCURRENT)
    return _semaphore


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def require_rate_limit(request: Request) -> None:
    """FastAPI dependency: enforce per-IP rate limiting on /query."""
    client_ip = request.client.host if request.client else "unknown"
    limiter = _get_rate_limiter()
    allowed, retry_after = limiter.is_allowed(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded. "
                f"Maximum {limiter.max_requests} requests "
                f"per {limiter.window_seconds} seconds."
            ),
            headers={"Retry-After": str(retry_after)},
        )


async def require_ollama_slot() -> AsyncGenerator[None, None]:
    """FastAPI dependency: acquire a concurrency slot for Ollama.

    Yields when a slot is available. Raises 429 if all slots are busy
    and the wait exceeds 5 seconds.
    """
    sem = _get_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=5.0)
    except TimeoutError:
        raise HTTPException(
            status_code=429,
            detail="LLM is busy processing other requests. Please try again shortly.",
            headers={"Retry-After": "10"},
        ) from None
    try:
        yield
    finally:
        sem.release()


# ---------------------------------------------------------------------------
# Testing helpers
# ---------------------------------------------------------------------------


def reset_rate_limiter() -> None:
    """Reset the rate limiter singleton. For testing only."""
    global _rate_limiter
    _rate_limiter = None


def reset_semaphore() -> None:
    """Reset the semaphore singleton. For testing only."""
    global _semaphore
    _semaphore = None
