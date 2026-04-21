"""Deterministic mock price generator (opt-in fallback, never primary).

Produces geometric Brownian motion bars seeded by ``hash(ticker)`` so every
call with the same ticker / window yields byte-identical output. Mock is only
activated when ``USE_MOCK_FALLBACK=true`` AND both Alpha Vantage and Yahoo
have failed — never otherwise. SPEC §0 explicitly warns against silent
fake-data bugs in production.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from typing import Any

from app.data.calendar import last_trading_day_on_or_before

logger = logging.getLogger(__name__)

PROVIDER_NAME = "mock"


def _seed(ticker: str) -> int:
    digest = hashlib.sha256(ticker.upper().encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


class _DeterministicRandom:
    """Tiny xoroshiro128+-style PRNG. Good enough for fixture data."""

    def __init__(self, seed: int) -> None:
        s = seed or 1
        self._s0 = (s * 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        self._s1 = ((s ^ 0xBF58476D1CE4E5B9) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF

    def _rotl(self, x: int, k: int) -> int:
        return ((x << k) | (x >> (64 - k))) & 0xFFFFFFFFFFFFFFFF

    def next_uint64(self) -> int:
        s0, s1 = self._s0, self._s1
        result = (s0 + s1) & 0xFFFFFFFFFFFFFFFF
        s1 ^= s0
        self._s0 = self._rotl(s0, 55) ^ s1 ^ ((s1 << 14) & 0xFFFFFFFFFFFFFFFF)
        self._s1 = self._rotl(s1, 36)
        return result

    def random(self) -> float:
        return self.next_uint64() / 2**64

    def normal(self) -> float:
        # Box-Muller, deterministic.
        import math

        u1 = max(self.random(), 1e-15)
        u2 = self.random()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _target_profile(ticker: str) -> tuple[float, float, float]:
    """Return (start_price, annualized_drift, annualized_vol) for ``ticker``."""

    profile = {
        "AAPL": (180.0, 0.22, 0.27),
        "MSFT": (380.0, 0.23, 0.26),
        "NVDA": (140.0, 0.60, 0.50),
        "JPM": (210.0, 0.14, 0.26),
        "XOM": (115.0, 0.12, 0.32),
        "SPY": (580.0, 0.10, 0.18),
    }
    if ticker.upper() in profile:
        return profile[ticker.upper()]
    rng = _DeterministicRandom(_seed(ticker))
    start = 50 + rng.random() * 300
    drift = 0.05 + rng.random() * 0.20
    vol = 0.18 + rng.random() * 0.25
    return start, drift, vol


def generate_daily_bars(
    ticker: str,
    *,
    lookback_years: int,
    end: Date | None = None,
) -> list[dict[str, Any]]:
    """Generate a deterministic daily OHLCV series for ``ticker``.

    The series ends at ``end`` (default: last NYSE session on or before today)
    and spans ``lookback_years`` calendar years of trading sessions.
    """

    if lookback_years <= 0:
        raise ValueError("lookback_years must be positive")

    end_date = last_trading_day_on_or_before(end or datetime.now(UTC).date())
    start_date = end_date - timedelta(days=int(lookback_years * 366))

    import pandas_market_calendars as mcal

    cal = mcal.get_calendar("NYSE")
    schedule = cal.schedule(start_date=start_date, end_date=end_date)
    session_dates: list[Date] = [
        ts.date() if hasattr(ts, "date") else ts for ts in schedule.index
    ]
    if not session_dates:
        return []

    start_price, annual_drift, annual_vol = _target_profile(ticker)
    rng = _DeterministicRandom(_seed(ticker))
    dt = 1.0 / 252.0
    price = start_price

    bars: list[dict[str, Any]] = []
    for day in session_dates:
        import math

        shock = rng.normal()
        ret = (annual_drift - 0.5 * annual_vol**2) * dt + annual_vol * math.sqrt(dt) * shock
        new_close = max(0.01, price * math.exp(ret))

        open_ = price * (1 + 0.002 * (rng.random() - 0.5))
        high = max(open_, new_close) * (1 + 0.004 * rng.random())
        low = min(open_, new_close) * (1 - 0.004 * rng.random())
        volume = int(5_000_000 + rng.random() * 15_000_000)

        bars.append(
            {
                "date": day.isoformat(),
                "open": round(open_, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(new_close, 4),
                "volume": volume,
            }
        )
        price = new_close

    return bars


def generate_quote(ticker: str) -> dict[str, Any]:
    bars = generate_daily_bars(ticker, lookback_years=1)
    if not bars:
        raise ValueError(f"no mock bars for {ticker}")
    last = bars[-1]
    as_of_date = Date.fromisoformat(last["date"])
    return {
        "ticker": ticker,
        "price": last["close"],
        "as_of": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
    }


__all__ = ["PROVIDER_NAME", "generate_daily_bars", "generate_quote"]
