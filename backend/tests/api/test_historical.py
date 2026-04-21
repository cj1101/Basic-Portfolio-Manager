"""GET /api/historical."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_historical_default_params(api_client):
    resp = await api_client.get("/api/historical", params={"ticker": "AAPL"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["frequency"] == "daily"
    assert len(body["bars"]) > 100
    first = body["bars"][0]
    assert {"date", "open", "high", "low", "close", "volume"}.issubset(first.keys())
    assert resp.headers["X-Data-Source"] == "alpha-vantage"


async def test_historical_weekly_and_monthly(api_client):
    weekly = await api_client.get(
        "/api/historical", params={"ticker": "AAPL", "frequency": "weekly", "years": 5}
    )
    monthly = await api_client.get(
        "/api/historical", params={"ticker": "AAPL", "frequency": "monthly", "years": 5}
    )
    assert weekly.status_code == 200
    assert monthly.status_code == 200
    assert 200 <= len(weekly.json()["bars"]) <= 300
    assert 50 <= len(monthly.json()["bars"]) <= 70


async def test_historical_rejects_invalid_years(api_client):
    resp = await api_client.get(
        "/api/historical", params={"ticker": "AAPL", "years": 99}
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "INVALID_RETURN_WINDOW"


async def test_historical_rejects_invalid_frequency(api_client):
    resp = await api_client.get(
        "/api/historical", params={"ticker": "AAPL", "frequency": "hourly"}
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] in {"INVALID_RETURN_WINDOW"}
