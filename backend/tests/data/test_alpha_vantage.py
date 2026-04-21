"""AlphaVantageClient — respx-mocked contract tests + live-gated smoke test."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.data.cache import MarketCache
from app.data.clients.alpha_vantage import AlphaVantageClient
from app.data.rate_limit import AlphaVantageRateLimiter
from app.errors import ProviderUnavailableError, RateLimitError, UnknownTickerError


pytestmark = pytest.mark.asyncio

BASE_URL = "https://www.alphavantage.co/query"


async def _client(cache: MarketCache) -> AlphaVantageClient:
    limiter = AlphaVantageRateLimiter(cache, per_minute=1000, per_day=10_000)
    return AlphaVantageClient(api_key="test", rate_limiter=limiter, base_url=BASE_URL)


async def test_get_quote_happy_path(cache, load_fixture):
    payload = load_fixture("av_quote_aapl.json")
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))
        async with await _client(cache) as client:
            quote = await client.get_quote("AAPL")
    assert quote["ticker"] == "AAPL"
    assert quote["price"] == pytest.approx(228.52)
    assert quote["as_of"].date().isoformat() == "2024-11-21"


async def test_get_quote_unknown_ticker(cache, load_fixture):
    payload = load_fixture("av_quote_unknown.json")
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))
        async with await _client(cache) as client:
            with pytest.raises(UnknownTickerError):
                await client.get_quote("FAKE")


async def test_get_quote_soft_rate_limit(cache, load_fixture):
    payload = load_fixture("av_rate_limit_note.json")
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))
        async with await _client(cache) as client:
            with pytest.raises(RateLimitError):
                await client.get_quote("AAPL")


async def test_get_quote_http_429_maps_to_rate_limit(cache):
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "30"}, json={"Note": "slow down"})
        )
        async with await _client(cache) as client:
            with pytest.raises(RateLimitError) as excinfo:
                await client.get_quote("AAPL")
    assert excinfo.value.details["retryAfterSeconds"] == pytest.approx(30.0)


async def test_get_quote_server_error_becomes_unavailable(cache):
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(503, text="oops"))
        async with await _client(cache) as client:
            with pytest.raises(ProviderUnavailableError):
                await client.get_quote("AAPL")


async def test_get_historical_normalizes_and_sorts(cache, load_fixture):
    payload = load_fixture("av_historical_aapl_small.json")
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))
        async with await _client(cache) as client:
            bars = await client.get_historical_daily("AAPL")
    dates = [b["date"] for b in bars]
    assert dates == sorted(dates)
    assert bars[-1]["date"] == "2024-11-21"
    assert bars[-1]["close"] == pytest.approx(228.52)
    assert all(isinstance(b["volume"], int) for b in bars)


async def test_get_historical_unknown_ticker(cache):
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json={"Error Message": "Invalid API call"}))
        async with await _client(cache) as client:
            with pytest.raises(UnknownTickerError):
                await client.get_historical_daily("FAKE")


async def test_network_error_maps_to_unavailable(cache):
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(side_effect=httpx.ConnectError("dns"))
        async with await _client(cache) as client:
            with pytest.raises(ProviderUnavailableError):
                await client.get_quote("AAPL")


async def test_rate_limiter_daily_quota_enforced(cache):
    limiter = AlphaVantageRateLimiter(cache, per_minute=100, per_day=1)
    client = AlphaVantageClient(api_key="test", rate_limiter=limiter, base_url=BASE_URL)
    payload = {
        "Global Quote": {"05. price": "1.0", "07. latest trading day": "2024-11-21"}
    }
    async with respx.mock(assert_all_mocked=True) as mock:
        mock.get(BASE_URL).mock(return_value=httpx.Response(200, json=payload))
        async with client:
            await client.get_quote("AAPL")
            with pytest.raises(RateLimitError):
                await client.get_quote("AAPL")


@pytest.mark.live
async def test_live_quote_roundtrip(cache, isolated_settings):
    import os

    key = os.getenv("ALPHA_VANTAGE_API_KEY") or ""
    if not key or key == "test-key":
        pytest.skip("Live test needs a real ALPHA_VANTAGE_API_KEY")
    limiter = AlphaVantageRateLimiter(cache, per_minute=5, per_day=500)
    client = AlphaVantageClient(api_key=key, rate_limiter=limiter)
    async with client:
        quote = await client.get_quote("AAPL")
    assert quote["ticker"] == "AAPL"
    assert quote["price"] > 0
