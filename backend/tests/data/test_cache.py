"""MarketCache behaviour: persistence, TTL, coalescing, quota counters."""

from __future__ import annotations

import asyncio
from datetime import date as Date
from datetime import datetime, timezone

import pytest

from app.data.cache import MarketCache


pytestmark = pytest.mark.asyncio


async def test_quote_roundtrip_and_ttl(cache: MarketCache) -> None:
    as_of = datetime(2024, 11, 21, tzinfo=timezone.utc)
    await cache.put_quote("AAPL", 228.52, as_of, source="alpha-vantage")

    hit = await cache.get_quote("AAPL", ttl_seconds=3600)
    assert hit is not None
    assert hit.ticker == "AAPL"
    assert hit.price == pytest.approx(228.52)
    assert hit.source == "alpha-vantage"

    assert await cache.get_quote("AAPL", ttl_seconds=0) is None
    assert await cache.get_quote("MSFT", ttl_seconds=3600) is None


async def test_historical_roundtrip(cache: MarketCache) -> None:
    payload = {"bars": [{"date": "2024-11-21", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100}]}
    await cache.put_historical(
        "AAPL",
        "daily",
        Date(2024, 11, 21),
        lookback_years=5,
        payload=payload,
        source="alpha-vantage",
    )
    hit = await cache.get_historical("AAPL", "daily", Date(2024, 11, 21), 5)
    assert hit is not None
    assert hit.payload == payload
    assert hit.source == "alpha-vantage"

    miss = await cache.get_historical("AAPL", "daily", Date(2024, 11, 20), 5)
    assert miss is None


async def test_risk_free_rate_ttl(cache: MarketCache) -> None:
    as_of = datetime(2024, 11, 20, tzinfo=timezone.utc)
    await cache.put_risk_free_rate(0.0523, as_of, "FRED")

    fresh = await cache.get_risk_free_rate(ttl_seconds=3600)
    assert fresh is not None
    assert fresh.source == "FRED"
    assert fresh.rate == pytest.approx(0.0523)

    stale = await cache.get_risk_free_rate(ttl_seconds=0)
    assert stale is None


async def test_daily_quota_counter(cache: MarketCache) -> None:
    today = Date(2024, 11, 21)
    assert await cache.get_daily_quota("alpha_vantage", today) == 0
    for expected in range(1, 6):
        n = await cache.increment_daily_quota("alpha_vantage", today)
        assert n == expected
    await cache.reset_daily_quota("alpha_vantage", today)
    assert await cache.get_daily_quota("alpha_vantage", today) == 0


async def test_singleflight_coalesces_concurrent_callers(cache: MarketCache) -> None:
    counter = {"n": 0}
    ready = asyncio.Event()
    release = asyncio.Event()

    async def factory() -> int:
        counter["n"] += 1
        ready.set()
        await release.wait()
        return 42

    async def _run() -> int:
        return await cache.run_singleflight("k", factory)

    tasks = [asyncio.create_task(_run()) for _ in range(10)]
    await ready.wait()
    release.set()
    results = await asyncio.gather(*tasks)

    assert results == [42] * 10
    assert counter["n"] == 1


async def test_singleflight_propagates_exception(cache: MarketCache) -> None:
    calls = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def factory() -> int:
        calls["n"] += 1
        started.set()
        await release.wait()
        raise RuntimeError("boom")

    async def _run() -> int:
        return await cache.run_singleflight("k-err", factory)

    tasks = [asyncio.create_task(_run()) for _ in range(3)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(r, RuntimeError) for r in results)
    assert calls["n"] == 1


async def test_singleflight_releases_key_after_completion(cache: MarketCache) -> None:
    calls = {"n": 0}

    async def factory() -> int:
        calls["n"] += 1
        return calls["n"]

    v1 = await cache.run_singleflight("k-seq", factory)
    v2 = await cache.run_singleflight("k-seq", factory)
    assert v1 == 1
    assert v2 == 2
