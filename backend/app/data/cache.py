"""SQLite-backed cache for market data + in-process single-flight coalescing.

Tables
------
``quotes``
    Latest price snapshots, TTL = ``Settings.quote_cache_ttl_seconds``.
``historical``
    Normalized bar payloads keyed by ``(ticker, frequency, window_end)``.
    Historical windows are immutable — a bar that has already settled never
    changes — so cached rows are returned indefinitely once written.
``risk_free_rate``
    Singleton row keyed by ``'latest'``. TTL 24 h.
``daily_quota``
    Persists the Alpha Vantage 500-req/day counter across process restarts.

Request coalescing (SPEC §6) lives on the cache object itself so every data
module shares it. Parallel callers for the same ``(namespace, key)`` share a
single in-flight ``asyncio.Future``; only one upstream fetch runs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as Date
from pathlib import Path
from typing import Any, TypeVar

import aiosqlite

logger = logging.getLogger(__name__)

T = TypeVar("T")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    ticker TEXT PRIMARY KEY,
    price REAL NOT NULL,
    as_of TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical (
    ticker TEXT NOT NULL,
    frequency TEXT NOT NULL,
    window_end TEXT NOT NULL,
    lookback_years INTEGER NOT NULL,
    payload TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (ticker, frequency, window_end, lookback_years)
);

CREATE TABLE IF NOT EXISTS risk_free_rate (
    id TEXT PRIMARY KEY,
    rate REAL NOT NULL,
    as_of TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_quota (
    provider TEXT NOT NULL,
    quota_date TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, quota_date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (ticker, kind)
);
"""


@dataclass(slots=True)
class CachedQuote:
    ticker: str
    price: float
    as_of: datetime
    fetched_at: float
    source: str


@dataclass(slots=True)
class CachedHistorical:
    ticker: str
    frequency: str
    window_end: Date
    lookback_years: int
    payload: dict
    fetched_at: float
    source: str


@dataclass(slots=True)
class CachedRiskFreeRate:
    rate: float
    as_of: datetime
    source: str
    fetched_at: float


class MarketCache:
    """Thread-safe (single-process) market-data cache + single-flight dedupe."""

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None
        self._init_lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._inflight_lock = asyncio.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    async def connect(self) -> None:
        async with self._init_lock:
            if self._conn is not None:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._conn.executescript(_SCHEMA)
            await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _ensure(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self.connect()
        assert self._conn is not None
        return self._conn

    # ----- quotes ---------------------------------------------------------

    async def get_quote(self, ticker: str, ttl_seconds: int) -> CachedQuote | None:
        conn = await self._ensure()
        async with conn.execute(
            "SELECT ticker, price, as_of, fetched_at, source FROM quotes WHERE ticker = ?",
            (ticker,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if _expired(row["fetched_at"], ttl_seconds):
            return None
        return CachedQuote(
            ticker=row["ticker"],
            price=row["price"],
            as_of=_parse_iso(row["as_of"]),
            fetched_at=row["fetched_at"],
            source=row["source"],
        )

    async def put_quote(self, ticker: str, price: float, as_of: datetime, source: str) -> None:
        conn = await self._ensure()
        await conn.execute(
            """
            INSERT INTO quotes (ticker, price, as_of, fetched_at, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                price = excluded.price,
                as_of = excluded.as_of,
                fetched_at = excluded.fetched_at,
                source = excluded.source
            """,
            (ticker, price, _to_iso(as_of), time.time(), source),
        )
        await conn.commit()

    # ----- historical -----------------------------------------------------

    async def get_historical(
        self,
        ticker: str,
        frequency: str,
        window_end: Date,
        lookback_years: int,
    ) -> CachedHistorical | None:
        conn = await self._ensure()
        async with conn.execute(
            """
            SELECT ticker, frequency, window_end, lookback_years, payload, fetched_at, source
            FROM historical
            WHERE ticker = ? AND frequency = ? AND window_end = ? AND lookback_years = ?
            """,
            (ticker, frequency, window_end.isoformat(), lookback_years),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return CachedHistorical(
            ticker=row["ticker"],
            frequency=row["frequency"],
            window_end=Date.fromisoformat(row["window_end"]),
            lookback_years=row["lookback_years"],
            payload=json.loads(row["payload"]),
            fetched_at=row["fetched_at"],
            source=row["source"],
        )

    async def put_historical(
        self,
        ticker: str,
        frequency: str,
        window_end: Date,
        lookback_years: int,
        payload: dict,
        source: str,
    ) -> None:
        conn = await self._ensure()
        await conn.execute(
            """
            INSERT INTO historical (ticker, frequency, window_end, lookback_years, payload, fetched_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, frequency, window_end, lookback_years) DO UPDATE SET
                payload = excluded.payload,
                fetched_at = excluded.fetched_at,
                source = excluded.source
            """,
            (
                ticker,
                frequency,
                window_end.isoformat(),
                lookback_years,
                json.dumps(payload, sort_keys=True),
                time.time(),
                source,
            ),
        )
        await conn.commit()

    # ----- risk-free rate -------------------------------------------------

    async def get_risk_free_rate(self, ttl_seconds: int) -> CachedRiskFreeRate | None:
        conn = await self._ensure()
        async with conn.execute(
            "SELECT rate, as_of, source, fetched_at FROM risk_free_rate WHERE id = 'latest'"
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if _expired(row["fetched_at"], ttl_seconds):
            return None
        return CachedRiskFreeRate(
            rate=row["rate"],
            as_of=_parse_iso(row["as_of"]),
            source=row["source"],
            fetched_at=row["fetched_at"],
        )

    # ----- fundamentals (Alpha Vantage) ----------------------------------

    FUNDAMENTALS_TTL_SECONDS: int = 7 * 24 * 3600

    async def get_fundamentals(self, ticker: str, kind: str) -> dict[str, Any] | None:
        conn = await self._ensure()
        async with conn.execute(
            "SELECT payload, fetched_at, source FROM fundamentals WHERE ticker = ? AND kind = ?",
            (ticker, kind),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if _expired(row["fetched_at"], self.FUNDAMENTALS_TTL_SECONDS):
            return None
        return json.loads(row["payload"])

    async def put_fundamentals(self, ticker: str, kind: str, payload: dict, source: str) -> None:
        conn = await self._ensure()
        await conn.execute(
            """
            INSERT INTO fundamentals (ticker, kind, payload, fetched_at, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(ticker, kind) DO UPDATE SET
                payload = excluded.payload,
                fetched_at = excluded.fetched_at,
                source = excluded.source
            """,
            (ticker, kind, json.dumps(payload, sort_keys=True), time.time(), source),
        )
        await conn.commit()

    async def put_risk_free_rate(self, rate: float, as_of: datetime, source: str) -> None:
        conn = await self._ensure()
        await conn.execute(
            """
            INSERT INTO risk_free_rate (id, rate, as_of, source, fetched_at)
            VALUES ('latest', ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                rate = excluded.rate,
                as_of = excluded.as_of,
                source = excluded.source,
                fetched_at = excluded.fetched_at
            """,
            (rate, _to_iso(as_of), source, time.time()),
        )
        await conn.commit()

    # ----- daily quota (used by rate_limit.py) ----------------------------

    async def get_daily_quota(self, provider: str, quota_date: Date) -> int:
        conn = await self._ensure()
        async with conn.execute(
            "SELECT count FROM daily_quota WHERE provider = ? AND quota_date = ?",
            (provider, quota_date.isoformat()),
        ) as cur:
            row = await cur.fetchone()
        return int(row["count"]) if row else 0

    async def increment_daily_quota(self, provider: str, quota_date: Date) -> int:
        conn = await self._ensure()
        await conn.execute(
            """
            INSERT INTO daily_quota (provider, quota_date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(provider, quota_date) DO UPDATE SET count = count + 1
            """,
            (provider, quota_date.isoformat()),
        )
        await conn.commit()
        return await self.get_daily_quota(provider, quota_date)

    async def reset_daily_quota(self, provider: str, quota_date: Date) -> None:
        conn = await self._ensure()
        await conn.execute(
            "DELETE FROM daily_quota WHERE provider = ? AND quota_date = ?",
            (provider, quota_date.isoformat()),
        )
        await conn.commit()

    # ----- single-flight --------------------------------------------------

    @asynccontextmanager
    async def singleflight(self, key: str):
        """Context manager yielding a Future for ``key``.

        Usage::

            async with cache.singleflight(key) as ctx:
                if ctx.leader:
                    try:
                        value = await upstream()
                        ctx.set_result(value)
                    except Exception as exc:
                        ctx.set_exception(exc)
                        raise
                else:
                    value = await ctx.wait()
        """

        async with self._inflight_lock:
            future = self._inflight.get(key)
            leader = future is None
            if leader:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future

        ctx = _SingleflightContext(self, key, future, leader)
        try:
            yield ctx
        finally:
            if leader:
                async with self._inflight_lock:
                    self._inflight.pop(key, None)
                if not future.done():  # leader failed to resolve — unblock waiters
                    future.set_exception(
                        RuntimeError(f"singleflight leader exited without resolving {key}")
                    )

    async def run_singleflight(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        """Convenience wrapper: run ``factory()`` deduped by ``key``."""

        async with self.singleflight(key) as ctx:
            if ctx.leader:
                try:
                    value = await factory()
                except BaseException as exc:
                    ctx.set_exception(exc)
                    raise
                ctx.set_result(value)
                return value
            return await ctx.wait()


class _SingleflightContext:
    __slots__ = ("_cache", "_future", "_key", "leader")

    def __init__(
        self,
        cache: MarketCache,
        key: str,
        future: asyncio.Future[Any],
        leader: bool,
    ) -> None:
        self._cache = cache
        self._key = key
        self._future = future
        self.leader = leader

    def set_result(self, value: Any) -> None:
        if not self._future.done():
            self._future.set_result(value)

    def set_exception(self, exc: BaseException) -> None:
        if not self._future.done():
            self._future.set_exception(exc)

    async def wait(self) -> Any:
        return await self._future


def _expired(fetched_at: float, ttl_seconds: int) -> bool:
    if ttl_seconds <= 0:
        return True
    return (time.time() - fetched_at) > ttl_seconds


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "CachedHistorical",
    "CachedQuote",
    "CachedRiskFreeRate",
    "MarketCache",
]
