"""GET /api/risk-free-rate."""

from __future__ import annotations

import pytest

from app.errors import ProviderUnavailableError

pytestmark = pytest.mark.asyncio


async def test_risk_free_rate_fred(api_client):
    resp = await api_client.get("/api/risk-free-rate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "FRED"
    assert body["rate"] == pytest.approx(0.0462)
    assert "asOf" in body
    assert resp.headers["X-Data-Source"] == "FRED"


async def test_risk_free_rate_fallback(api_client, api_state):
    api_state.fred.exc = ProviderUnavailableError("fred", "down")
    resp = await api_client.get("/api/risk-free-rate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "FALLBACK"
    assert body["rate"] > 0
    assert "X-Data-Warnings" in resp.headers
