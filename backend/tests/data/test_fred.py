"""FRED client — respx-mocked + live-gated."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.data.clients.fred import FredClient
from app.errors import ProviderUnavailableError


pytestmark = pytest.mark.asyncio

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


async def test_dgs3mo_converts_percent_to_decimal(load_fixture):
    payload = load_fixture("fred_dgs3mo.json")
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))
        async with FredClient(api_key="k", base_url=BASE_URL) as client:
            result = await client.get_latest_dgs3mo()
    assert result["source"] == "FRED"
    assert result["rate"] == pytest.approx(0.0462)
    assert result["as_of"].date().isoformat() == "2024-11-20"


async def test_dgs3mo_skips_dots(load_fixture):
    payload = load_fixture("fred_dgs3mo_dots.json")
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))
        async with FredClient(api_key="k", base_url=BASE_URL) as client:
            result = await client.get_latest_dgs3mo()
    assert result["rate"] == pytest.approx(0.0459)
    assert result["as_of"].date().isoformat() == "2024-11-19"


async def test_dgs3mo_all_missing_raises():
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json={"observations": [{"date": "2024-11-21", "value": "."}]}))
        async with FredClient(api_key="k", base_url=BASE_URL) as client:
            with pytest.raises(ProviderUnavailableError):
                await client.get_latest_dgs3mo()


async def test_dgs3mo_http_500_becomes_unavailable():
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(500, text="upstream fail"))
        async with FredClient(api_key="k", base_url=BASE_URL) as client:
            with pytest.raises(ProviderUnavailableError):
                await client.get_latest_dgs3mo()


async def test_dgs3mo_network_error_becomes_unavailable():
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(side_effect=httpx.ConnectError("dns"))
        async with FredClient(api_key="k", base_url=BASE_URL) as client:
            with pytest.raises(ProviderUnavailableError):
                await client.get_latest_dgs3mo()


@pytest.mark.live
async def test_live_fred_fetch(isolated_settings):
    import os

    key = os.getenv("FRED_API_KEY") or ""
    if not key or key == "fred-test-key":
        pytest.skip("Live test needs a real FRED_API_KEY")
    async with FredClient(api_key=key) as client:
        result = await client.get_latest_dgs3mo()
    assert 0.0 <= result["rate"] <= 0.2  # 0-20% annualized sanity
