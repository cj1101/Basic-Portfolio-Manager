"""Rate-limiter behaviour: token refill, daily quota."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.data.cache import MarketCache
from app.data.rate_limit import AlphaVantageRateLimiter, TokenBucket
from app.errors import RateLimitError


pytestmark = pytest.mark.asyncio


async def test_token_bucket_starts_full_and_drains() -> None:
    bucket = TokenBucket(capacity=3, window_seconds=60)
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()


async def test_token_bucket_refills_over_time(monkeypatch) -> None:
    bucket = TokenBucket(capacity=5, window_seconds=60)
    # drain
    for _ in range(5):
        assert bucket.try_acquire()
    assert not bucket.try_acquire()

    # advance mono time by 30 seconds -> 2.5 tokens refilled
    import time as _time

    base = _time.monotonic()
    monkeypatch.setattr(_time, "monotonic", lambda: base + 30.0)
    # TokenBucket uses time.monotonic() via `import time` at module level,
    # so patch its module reference too.
    from app.data import rate_limit as rl_mod

    monkeypatch.setattr(rl_mod.time, "monotonic", lambda: base + 30.0)
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()


async def test_daily_quota_raises_when_exhausted(cache: MarketCache) -> None:
    limiter = AlphaVantageRateLimiter(cache, per_minute=100, per_day=3, minute_window=60.0)
    for _ in range(3):
        await limiter.acquire(wait=False)
    assert await limiter.remaining_today() == 0
    with pytest.raises(RateLimitError) as excinfo:
        await limiter.acquire(wait=False)
    assert excinfo.value.details["scope"] == "day"


async def test_minute_limit_raises_when_not_waiting(cache: MarketCache) -> None:
    limiter = AlphaVantageRateLimiter(cache, per_minute=2, per_day=500, minute_window=60.0)
    await limiter.acquire(wait=False)
    await limiter.acquire(wait=False)
    with pytest.raises(RateLimitError) as excinfo:
        await limiter.acquire(wait=False)
    assert excinfo.value.details["scope"] == "minute"


async def test_waiting_acquire_eventually_succeeds(cache: MarketCache) -> None:
    limiter = AlphaVantageRateLimiter(cache, per_minute=50, per_day=500, minute_window=1.0)
    # 50/s refill => we can do 3 acquires within a short budget
    await asyncio.wait_for(limiter.acquire(), timeout=2.0)
    await asyncio.wait_for(limiter.acquire(), timeout=2.0)
    await asyncio.wait_for(limiter.acquire(), timeout=2.0)
