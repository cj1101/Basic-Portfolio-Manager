"""Concurrency stress test for ``MarketCache.run_singleflight``.

The single-flight wrapper deduplicates in-flight calls for a given key, so
200 concurrent fetches of the same ``(ticker, frequency, years)`` tuple
must result in **exactly one** call to the underlying factory. Anything
more wastes an Alpha Vantage token + cache write.
"""

from __future__ import annotations

import asyncio

import pytest

from app.data.cache import MarketCache

pytestmark = pytest.mark.asyncio


async def test_singleflight_collapses_concurrent_callers(cache: MarketCache) -> None:
    call_count = 0
    barrier = asyncio.Event()
    concurrency = 200

    async def factory() -> str:
        nonlocal call_count
        call_count += 1
        # Give every coroutine time to pile up behind the leader.
        await barrier.wait()
        return "computed"

    async def caller() -> str:
        return await cache.run_singleflight("key-A", factory)

    tasks = [asyncio.create_task(caller()) for _ in range(concurrency)]
    # Let all callers register as followers, then release the leader.
    await asyncio.sleep(0.05)
    barrier.set()
    results = await asyncio.gather(*tasks)

    assert results == ["computed"] * concurrency
    assert call_count == 1


async def test_singleflight_different_keys_run_in_parallel(
    cache: MarketCache,
) -> None:
    """Singleflight must dedupe per-key, not globally."""

    started = asyncio.Event()
    release = asyncio.Event()
    ran: dict[str, int] = {"A": 0, "B": 0}

    async def factory(key: str) -> str:
        ran[key] += 1
        started.set()
        await release.wait()
        return key

    task_a = asyncio.create_task(
        cache.run_singleflight("key-A", lambda: factory("A"))
    )
    task_b = asyncio.create_task(
        cache.run_singleflight("key-B", lambda: factory("B"))
    )

    await started.wait()
    # Both factories should be in flight simultaneously.
    await asyncio.sleep(0.01)
    release.set()
    a, b = await asyncio.gather(task_a, task_b)

    assert a == "A"
    assert b == "B"
    assert ran == {"A": 1, "B": 1}


async def test_singleflight_propagates_exception_to_followers(
    cache: MarketCache,
) -> None:
    """When the leader raises, every follower must see the same exception."""

    call_count = 0
    barrier = asyncio.Event()
    concurrency = 50

    class BoomError(RuntimeError):
        pass

    async def factory() -> str:
        nonlocal call_count
        call_count += 1
        await barrier.wait()
        raise BoomError("boom")

    async def caller() -> BaseException | None:
        try:
            await cache.run_singleflight("key-err", factory)
        except BoomError as exc:
            return exc
        return None

    tasks = [asyncio.create_task(caller()) for _ in range(concurrency)]
    await asyncio.sleep(0.05)
    barrier.set()
    results = await asyncio.gather(*tasks)

    assert call_count == 1
    assert all(isinstance(r, BoomError) for r in results)
