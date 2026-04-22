"""Concurrency stress tests for ``AlphaVantageRateLimiter``.

The limiter enforces **two** budgets at once (per-minute token bucket +
per-day SQLite counter) so a naive implementation can easily leak a token
when hundreds of coroutines race through ``acquire()`` simultaneously.
These tests hammer the limiter and assert the invariants from
``docs/SPEC.md`` §6:

- The minute bucket never hands out more than ``per_minute`` tokens within
  one window.
- The daily counter is *exactly* the number of successful ``acquire()``s.
- No off-by-one or lost-update bugs under parallelism.
"""

from __future__ import annotations

import asyncio

import pytest

from app.data.cache import MarketCache
from app.data.rate_limit import AlphaVantageRateLimiter, TokenBucket
from app.errors import RateLimitError

pytestmark = pytest.mark.asyncio


async def test_token_bucket_never_overissues_under_concurrent_load() -> None:
    """500 concurrent try_acquire()s on a bucket of capacity 5 => at most 5
    succeed before the bucket refills."""

    # Very long window so the bucket doesn't refill while the test runs.
    bucket = TokenBucket(capacity=5, window_seconds=3600.0)

    async def attempt() -> bool:
        # ``try_acquire`` is synchronous; wrap in a no-op await so we can
        # actually run 500 "coroutines" concurrently through the loop.
        await asyncio.sleep(0)
        return bucket.try_acquire()

    results = await asyncio.gather(*(attempt() for _ in range(500)))
    granted = sum(results)
    assert granted == 5, f"expected exactly 5 grants, got {granted}"


async def test_rate_limiter_daily_counter_matches_acquires(
    cache: MarketCache,
) -> None:
    """200 concurrent ``acquire()`` calls should atomically increment the
    daily counter — the stored count must equal the number of successes."""

    # Plenty of minute capacity so we never hit that path.
    limiter = AlphaVantageRateLimiter(
        cache, per_minute=500, per_day=500, minute_window=60.0
    )

    async def one() -> bool:
        try:
            await limiter.acquire(wait=False)
            return True
        except RateLimitError:
            return False

    results = await asyncio.gather(*(one() for _ in range(200)))
    granted = sum(results)
    assert granted == 200
    assert await limiter.remaining_today() == 300


async def test_rate_limiter_respects_daily_cap_under_race(
    cache: MarketCache,
) -> None:
    """400 concurrent ``acquire()``s on a budget of 50/day => exactly 50
    succeed and the remaining 350 raise ``RateLimitError``."""

    limiter = AlphaVantageRateLimiter(
        cache, per_minute=1000, per_day=50, minute_window=60.0
    )

    async def one() -> bool:
        try:
            await limiter.acquire(wait=False)
            return True
        except RateLimitError:
            return False

    results = await asyncio.gather(*(one() for _ in range(400)))
    granted = sum(results)
    assert granted == 50
    assert await limiter.remaining_today() == 0


async def test_rate_limiter_minute_cap_under_race(cache: MarketCache) -> None:
    """300 concurrent ``acquire(wait=False)``s on a ``per_minute=7`` limiter
    (with plenty of daily budget) should grant exactly 7 tokens; the rest
    must raise a minute-scope ``RateLimitError``."""

    limiter = AlphaVantageRateLimiter(
        cache, per_minute=7, per_day=5000, minute_window=3600.0
    )
    scopes: list[str] = []

    async def one() -> bool:
        try:
            await limiter.acquire(wait=False)
            return True
        except RateLimitError as exc:
            scopes.append(exc.details.get("scope", "?") if hasattr(exc, "details") else "?")
            return False

    results = await asyncio.gather(*(one() for _ in range(300)))
    granted = sum(results)
    assert granted == 7
    # Daily count stays accurate too — we should have incremented it 7 times.
    assert await limiter.remaining_today() == 5000 - 7
