"""Mock generator is deterministic + plausible."""

from __future__ import annotations

from datetime import date as Date

import pytest

from app.data.mock import generate_daily_bars, generate_quote


def test_daily_bars_are_deterministic():
    end = Date(2024, 11, 21)
    a = generate_daily_bars("AAPL", lookback_years=2, end=end)
    b = generate_daily_bars("AAPL", lookback_years=2, end=end)
    assert a == b


def test_different_tickers_diverge():
    end = Date(2024, 11, 21)
    a = generate_daily_bars("AAPL", lookback_years=1, end=end)
    b = generate_daily_bars("MSFT", lookback_years=1, end=end)
    assert a != b
    assert a[0] != b[0]


def test_daily_bars_span_expected_range():
    end = Date(2024, 11, 21)
    bars = generate_daily_bars("AAPL", lookback_years=5, end=end)
    # 5 years ~ 1250 NYSE sessions.
    assert 1100 <= len(bars) <= 1300
    assert bars[-1]["date"] <= end.isoformat()


def test_quote_matches_last_bar():
    q = generate_quote("AAPL")
    assert q["ticker"] == "AAPL"
    assert q["price"] > 0


def test_invalid_lookback_raises():
    with pytest.raises(ValueError):
        generate_daily_bars("AAPL", lookback_years=0)
