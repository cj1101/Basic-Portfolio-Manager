"""Sync unit tests (no asyncio) — avoids global pytest-asyncio mark on helpers."""

from __future__ import annotations

import pytest

from app.data.service import _normalize_ticker, _resample_bars
from app.errors import InvalidReturnWindowError


def test_normalize_ticker_accepts_gspc_index():
    assert _normalize_ticker("^GSPC") == "^GSPC"


def test_normalize_ticker_rejects_malformed_index():
    with pytest.raises(InvalidReturnWindowError):
        _normalize_ticker("^")


def test_resample_bars_propagates_close_nominal():
    daily = [
        {
            "date": "2024-01-02",
            "open": 1.0,
            "high": 1.1,
            "low": 1.0,
            "close": 10.0,
            "close_nominal": 9.0,
            "volume": 100,
        },
        {
            "date": "2024-01-30",
            "open": 1.0,
            "high": 1.1,
            "low": 1.0,
            "close": 11.0,
            "close_nominal": 10.0,
            "volume": 100,
        },
    ]
    out = _resample_bars(daily, "ME")
    assert len(out) == 1
    assert out[0]["close"] == 11.0
    assert out[0]["close_nominal"] == 10.0
