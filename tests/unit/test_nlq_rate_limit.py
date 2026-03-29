"""Unit tests for NLQ rate limiting and concurrency control."""

import asyncio
import contextlib
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.nlq.rate_limit import (
    SlidingWindowRateLimiter,
    require_ollama_slot,
    require_rate_limit,
    reset_rate_limiter,
    reset_semaphore,
)


class TestSlidingWindowRateLimiter:
    """Tests for the in-memory sliding window rate limiter."""

    def test_allows_requests_under_limit(self):
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = limiter.is_allowed("192.168.1.1")
            assert allowed is True

    def test_blocks_requests_over_limit(self):
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed("192.168.1.1")
        allowed, retry_after = limiter.is_allowed("192.168.1.1")
        assert allowed is False
        assert retry_after >= 1

    def test_different_keys_tracked_independently(self):
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.is_allowed("ip_a")[0] is True
        assert limiter.is_allowed("ip_b")[0] is True
        assert limiter.is_allowed("ip_a")[0] is False

    def test_window_expiration_allows_new_requests(self):
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("x")
        assert limiter.is_allowed("x")[0] is False

        # Simulate time passing beyond the window
        with patch("api.nlq.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = limiter._requests["x"][0] + 61
            allowed, _ = limiter.is_allowed("x")
            assert allowed is True

    def test_returns_positive_retry_after(self):
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=30)
        limiter.is_allowed("x")
        _, retry_after = limiter.is_allowed("x")
        assert retry_after > 0

    def test_retry_after_is_at_least_one(self):
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=1)
        limiter.is_allowed("x")
        _, retry_after = limiter.is_allowed("x")
        assert retry_after >= 1

    def test_allows_again_at_boundary(self):
        """Requests are allowed once the oldest timestamp exits the window."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10)
        limiter.is_allowed("ip")
        limiter.is_allowed("ip")
        assert limiter.is_allowed("ip")[0] is False

        with patch("api.nlq.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = limiter._requests["ip"][0] + 11
            allowed, _ = limiter.is_allowed("ip")
            assert allowed is True


class TestRequireRateLimit:
    """Tests for the require_rate_limit FastAPI dependency."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        reset_rate_limiter()
        yield
        reset_rate_limiter()

    def test_allows_request_under_limit(self):
        with patch("api.nlq.rate_limit.config") as mock_config:
            mock_config.NLQ_RATE_LIMIT = 5
            mock_config.NLQ_RATE_LIMIT_WINDOW = 60
            mock_request = _make_request("10.0.0.1")
            asyncio.run(require_rate_limit(mock_request))

    def test_raises_429_when_limit_exceeded(self):
        async def _run():
            mock_request = _make_request("10.0.0.2")
            await require_rate_limit(mock_request)
            await require_rate_limit(mock_request)
            with pytest.raises(HTTPException) as exc_info:
                await require_rate_limit(mock_request)
            assert exc_info.value.status_code == 429
            assert "Retry-After" in exc_info.value.headers

        with patch("api.nlq.rate_limit.config") as mock_config:
            mock_config.NLQ_RATE_LIMIT = 2
            mock_config.NLQ_RATE_LIMIT_WINDOW = 60
            asyncio.run(_run())

    def test_different_ips_have_separate_limits(self):
        async def _run():
            await require_rate_limit(_make_request("10.0.0.3"))
            await require_rate_limit(_make_request("10.0.0.4"))

        with patch("api.nlq.rate_limit.config") as mock_config:
            mock_config.NLQ_RATE_LIMIT = 1
            mock_config.NLQ_RATE_LIMIT_WINDOW = 60
            asyncio.run(_run())


async def _exhaust_generator(gen):
    """Advance an async generator past yield, triggering cleanup."""
    with contextlib.suppress(StopAsyncIteration):
        await gen.__anext__()


class TestRequireOllamaSlot:
    """Tests for the require_ollama_slot concurrency dependency."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        reset_semaphore()
        yield
        reset_semaphore()

    def test_allows_when_slot_available(self):
        async def _run():
            gen = require_ollama_slot()
            await gen.__anext__()
            await _exhaust_generator(gen)

        with patch("api.nlq.rate_limit.config") as mock_config:
            mock_config.NLQ_MAX_CONCURRENT = 2
            asyncio.run(_run())

    def test_raises_429_when_all_slots_busy(self):
        async def _run():
            # Occupy the only slot
            gen1 = require_ollama_slot()
            await gen1.__anext__()

            # Second request should get 429
            def _timeout(coro, **kwargs):
                coro.close()  # prevent "coroutine never awaited" warning
                raise TimeoutError

            with patch(
                "api.nlq.rate_limit.asyncio.wait_for",
                side_effect=_timeout,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    gen2 = require_ollama_slot()
                    await gen2.__anext__()
                assert exc_info.value.status_code == 429

            # Clean up slot 1
            await _exhaust_generator(gen1)

        with patch("api.nlq.rate_limit.config") as mock_config:
            mock_config.NLQ_MAX_CONCURRENT = 1
            asyncio.run(_run())

    def test_slot_released_after_use(self):
        async def _run():
            # Use and release a slot
            gen1 = require_ollama_slot()
            await gen1.__anext__()
            await _exhaust_generator(gen1)

            # Should be able to acquire again
            gen2 = require_ollama_slot()
            await gen2.__anext__()
            await _exhaust_generator(gen2)

        with patch("api.nlq.rate_limit.config") as mock_config:
            mock_config.NLQ_MAX_CONCURRENT = 1
            asyncio.run(_run())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _MockRequest:
    def __init__(self, client_host: str) -> None:
        self.client = _MockClient(client_host)


def _make_request(host: str) -> _MockRequest:
    return _MockRequest(host)
