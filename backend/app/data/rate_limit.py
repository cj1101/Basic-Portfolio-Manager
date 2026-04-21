"""Token-bucket rate limiter + persistent daily quota for Alpha Vantage.

The Alpha Vantage free tier allows 5 requests/minute and 500 requests/day
(SPEC §6). We enforce both:

* The per-minute budget is an in-memory async token bucket — losing its state
  on restart is fine; the worst case is a 12-second wait.
* The per-day budget persists to SQLite via ``MarketCache`` so restarts can
  not accidentally blow past the 500/day cap.

Only ``app/data/clients/alpha_vantage.py`` is allowed to consume the bucket.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from datetime import date as Date

from app.data.cache import MarketCache
from app.errors import RateLimitError

logger = logging.getLogger(__name__)


class TokenBucket:
    """Leaky-bucket style async limiter.

    Capacity ``capacity`` tokens, refilled continuously at
    ``capacity / window_seconds`` tokens per second. ``acquire()`` waits until
    a token is available.
    """

    def __init__(self, capacity: int, window_seconds: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._capacity = capacity
        self._window = window_seconds
        self._refill_per_second = capacity / window_seconds
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
        self._last_refill = now

    def available(self) -> float:
        self._refill()
        return self._tokens

    def seconds_until_next_token(self) -> float:
        self._refill()
        if self._tokens >= 1:
            return 0.0
        deficit = 1 - self._tokens
        return deficit / self._refill_per_second

    async def acquire(self, *, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = self.seconds_until_next_token()
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("rate limit acquire timed out")
                wait = min(wait, remaining)
            await asyncio.sleep(max(wait, 0.0))

    def try_acquire(self) -> bool:
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


class AlphaVantageRateLimiter:
    """Combined per-minute + per-day limiter for Alpha Vantage."""

    PROVIDER = "alpha_vantage"

    def __init__(
        self,
        cache: MarketCache,
        *,
        per_minute: int = 5,
        per_day: int = 500,
        minute_window: float = 60.0,
    ) -> None:
        self._cache = cache
        self._per_day = per_day
        self._bucket = TokenBucket(capacity=per_minute, window_seconds=minute_window)
        self._day_lock = asyncio.Lock()

    @property
    def per_minute(self) -> int:
        return self._bucket.capacity

    @property
    def per_day(self) -> int:
        return self._per_day

    async def _current_daily_count(self, today: Date) -> int:
        return await self._cache.get_daily_quota(self.PROVIDER, today)

    async def acquire(self, *, wait: bool = True) -> None:
        """Consume one token. Raises ``RateLimitError`` if quota exhausted."""

        today = datetime.now(UTC).date()

        async with self._day_lock:
            count = await self._current_daily_count(today)
            if count >= self._per_day:
                seconds_to_midnight = _seconds_until_utc_midnight()
                raise RateLimitError(
                    self.PROVIDER,
                    seconds_to_midnight,
                    scope="day",
                )

            if wait:
                await self._bucket.acquire()
            else:
                if not self._bucket.try_acquire():
                    raise RateLimitError(
                        self.PROVIDER,
                        self._bucket.seconds_until_next_token(),
                        scope="minute",
                    )

            await self._cache.increment_daily_quota(self.PROVIDER, today)

    async def remaining_today(self) -> int:
        today = datetime.now(UTC).date()
        return max(0, self._per_day - await self._current_daily_count(today))


def _seconds_until_utc_midnight() -> float:
    now = datetime.now(UTC)
    tomorrow = (now + _ONE_DAY).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1.0, (tomorrow - now).total_seconds())


from datetime import timedelta as _TimeDelta

_ONE_DAY = _TimeDelta(days=1)


__all__ = ["AlphaVantageRateLimiter", "TokenBucket"]
