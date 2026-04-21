"""YahooClient — uses a stub ticker factory in unit tests, gated live run."""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.data.clients.yahoo import YahooClient
from app.errors import ProviderUnavailableError, UnknownTickerError


pytestmark = pytest.mark.asyncio


class _StubTicker:
    """Minimal yfinance.Ticker shim — history() returns a fixed DataFrame."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def history(self, **kwargs) -> pd.DataFrame:
        return self._frame


def _factory(frame: pd.DataFrame):
    def make(symbol: str) -> _StubTicker:
        return _StubTicker(frame)

    return make


def _frame(rows: list[tuple[str, float, float, float, float, int]]) -> pd.DataFrame:
    idx = [pd.Timestamp(r[0], tz="UTC") for r in rows]
    data = {
        "Open": [r[1] for r in rows],
        "High": [r[2] for r in rows],
        "Low": [r[3] for r in rows],
        "Close": [r[4] for r in rows],
        "Volume": [r[5] for r in rows],
    }
    return pd.DataFrame(data, index=idx)


async def test_yahoo_historical_normalizes():
    frame = _frame(
        [
            ("2024-11-18", 225.0, 229.7, 225.17, 228.02, 44_686_020),
            ("2024-11-19", 226.98, 230.16, 226.66, 228.28, 32_626_561),
            ("2024-11-20", 228.04, 229.93, 225.90, 229.00, 35_426_594),
            ("2024-11-21", 225.12, 229.74, 225.00, 228.52, 38_654_311),
        ]
    )
    client = YahooClient(ticker_factory=_factory(frame))
    bars = await client.get_historical_daily("AAPL", lookback_years=1)
    assert [b["date"] for b in bars] == [
        "2024-11-18",
        "2024-11-19",
        "2024-11-20",
        "2024-11-21",
    ]
    assert bars[-1]["close"] == pytest.approx(228.52)


async def test_yahoo_historical_empty_is_unknown():
    frame = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    client = YahooClient(ticker_factory=_factory(frame))
    with pytest.raises(UnknownTickerError):
        await client.get_historical_daily("FAKE", lookback_years=1)


async def test_yahoo_history_exception_wraps():
    class _Broken:
        def history(self, **kwargs):
            raise RuntimeError("boom")

    client = YahooClient(ticker_factory=lambda s: _Broken())
    with pytest.raises(ProviderUnavailableError):
        await client.get_historical_daily("AAPL", lookback_years=1)


async def test_yahoo_quote_uses_last_close():
    frame = _frame(
        [
            ("2024-11-20", 228.04, 229.93, 225.90, 229.00, 35_426_594),
            ("2024-11-21", 225.12, 229.74, 225.00, 228.52, 38_654_311),
        ]
    )
    client = YahooClient(ticker_factory=_factory(frame))
    q = await client.get_quote("AAPL")
    assert q["price"] == pytest.approx(228.52)
    assert q["as_of"].date() == Date(2024, 11, 21)


@pytest.mark.live
async def test_yahoo_live_roundtrip():
    import os

    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip()
    client = YahooClient()
    q = await client.get_quote("AAPL")
    assert q["price"] > 0
    bars = await client.get_historical_daily("AAPL", lookback_years=1)
    assert len(bars) > 100


# Silence unused-imports hints; these are used implicitly by pandas inference.
_ = datetime, timezone
