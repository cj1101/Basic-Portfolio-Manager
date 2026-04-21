"""DataService orchestration: fallback order, coalescing, cache TTL."""

from __future__ import annotations

import asyncio
from datetime import date as Date
from datetime import datetime, timezone

import pytest

from app.data.mock import generate_daily_bars
from app.data.service import DataService
from app.errors import ProviderUnavailableError, RateLimitError, UnknownTickerError
from app.schemas import ReturnFrequency


pytestmark = pytest.mark.asyncio


class _FakeAV:
    """Drop-in replacement for AlphaVantageClient."""

    def __init__(self, *, hist_result=None, quote_result=None, hist_exc=None, quote_exc=None):
        self.hist_calls = 0
        self.quote_calls = 0
        self._hist_result = hist_result
        self._quote_result = quote_result
        self._hist_exc = hist_exc
        self._quote_exc = quote_exc

    async def get_historical_daily(self, ticker: str, **kwargs):
        self.hist_calls += 1
        if self._hist_exc is not None:
            raise self._hist_exc
        return self._hist_result

    async def get_quote(self, ticker: str):
        self.quote_calls += 1
        if self._quote_exc is not None:
            raise self._quote_exc
        return self._quote_result

    async def close(self) -> None:
        return None


class _FakeYahoo:
    def __init__(self, *, hist_result=None, quote_result=None, hist_exc=None, quote_exc=None):
        self.hist_calls = 0
        self.quote_calls = 0
        self._hist_result = hist_result
        self._quote_result = quote_result
        self._hist_exc = hist_exc
        self._quote_exc = quote_exc

    async def get_historical_daily(self, ticker, *, lookback_years, end=None):
        self.hist_calls += 1
        if self._hist_exc is not None:
            raise self._hist_exc
        if self._hist_result is not None:
            return self._hist_result
        return generate_daily_bars(ticker, lookback_years=lookback_years, end=end)

    async def get_quote(self, ticker):
        self.quote_calls += 1
        if self._quote_exc is not None:
            raise self._quote_exc
        return self._quote_result

    async def close(self) -> None:
        return None


class _FakeFRED:
    def __init__(self, *, result=None, exc=None):
        self.calls = 0
        self._result = result
        self._exc = exc

    async def get_latest_dgs3mo(self):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._result

    async def close(self) -> None:
        return None


def _mock_bars_for(ticker: str, years: int = 5) -> list[dict]:
    return generate_daily_bars(ticker, lookback_years=years)


async def test_historical_uses_alpha_vantage_when_healthy(cache, isolated_settings):
    bars = _mock_bars_for("AAPL", years=5)
    av = _FakeAV(hist_result=bars)
    yahoo = _FakeYahoo()
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    result = await service.get_historical("AAPL", lookback_years=5)
    assert av.hist_calls == 1
    assert yahoo.hist_calls == 0
    assert result.source == "alpha-vantage"
    assert result.warnings == []
    assert len(result.bars) > 100


async def test_historical_falls_back_to_yahoo_on_rate_limit(cache, isolated_settings):
    av = _FakeAV(hist_exc=RateLimitError("alpha-vantage", 30.0, scope="minute"))
    yahoo = _FakeYahoo()
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    result = await service.get_historical("AAPL", lookback_years=5)
    assert av.hist_calls == 1
    assert yahoo.hist_calls == 1
    assert result.source == "yahoo"
    assert any("rate-limited" in w for w in result.warnings)


async def test_historical_unknown_ticker_propagates_when_both_fail(cache, isolated_settings):
    av = _FakeAV(hist_exc=UnknownTickerError("FAKE"))
    yahoo = _FakeYahoo(hist_exc=UnknownTickerError("FAKE"))
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    with pytest.raises(UnknownTickerError):
        await service.get_historical("FAKE", lookback_years=5)


async def test_historical_mock_fallback_when_enabled(cache, isolated_settings):
    av = _FakeAV(hist_exc=ProviderUnavailableError("alpha-vantage", "down"))
    yahoo = _FakeYahoo(hist_exc=ProviderUnavailableError("yahoo", "down"))
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=True,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    result = await service.get_historical("AAPL", lookback_years=5)
    assert result.source == "mock"
    assert any("mock" in w.lower() for w in result.warnings)


async def test_historical_raises_when_mock_disabled(cache, isolated_settings):
    av = _FakeAV(hist_exc=ProviderUnavailableError("alpha-vantage", "down"))
    yahoo = _FakeYahoo(hist_exc=ProviderUnavailableError("yahoo", "down"))
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    with pytest.raises(ProviderUnavailableError):
        await service.get_historical("AAPL", lookback_years=5)


async def test_historical_coalesces_concurrent_calls(cache, isolated_settings):
    bars = _mock_bars_for("AAPL", years=5)
    av = _FakeAV(hist_result=bars)
    yahoo = _FakeYahoo()
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    results = await asyncio.gather(
        *[service.get_historical("AAPL", lookback_years=5) for _ in range(8)]
    )
    assert len(results) == 8
    # First call fetches; others hit the in-flight future or the cache.
    assert av.hist_calls == 1


async def test_historical_cache_hit_second_time(cache, isolated_settings):
    bars = _mock_bars_for("AAPL", years=5)
    av = _FakeAV(hist_result=bars)
    yahoo = _FakeYahoo()
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    await service.get_historical("AAPL", lookback_years=5)
    await service.get_historical("AAPL", lookback_years=5)
    assert av.hist_calls == 1


async def test_historical_supports_weekly_and_monthly(cache, isolated_settings):
    bars = _mock_bars_for("AAPL", years=5)
    av = _FakeAV(hist_result=bars)
    yahoo = _FakeYahoo()
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    weekly = await service.get_historical(
        "AAPL", frequency=ReturnFrequency.WEEKLY, lookback_years=5
    )
    monthly = await service.get_historical(
        "AAPL", frequency=ReturnFrequency.MONTHLY, lookback_years=5
    )
    assert 200 <= len(weekly.bars) <= 300
    assert 50 <= len(monthly.bars) <= 70


async def test_quote_uses_alpha_vantage_when_healthy(cache, isolated_settings):
    av = _FakeAV(
        quote_result={
            "ticker": "AAPL",
            "price": 228.52,
            "as_of": datetime(2024, 11, 21, tzinfo=timezone.utc),
        }
    )
    yahoo = _FakeYahoo()
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    result = await service.get_quote("AAPL")
    assert result.source == "alpha-vantage"
    assert result.quote.price == pytest.approx(228.52)


async def test_quote_falls_back_to_yahoo(cache, isolated_settings):
    av = _FakeAV(quote_exc=ProviderUnavailableError("alpha-vantage", "down"))
    yahoo = _FakeYahoo(
        quote_result={
            "ticker": "AAPL",
            "price": 227.11,
            "as_of": datetime(2024, 11, 21, tzinfo=timezone.utc),
        }
    )
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    result = await service.get_quote("AAPL")
    assert result.source == "yahoo"


async def test_quote_cache_hit_avoids_new_calls(cache, isolated_settings):
    av = _FakeAV(
        quote_result={
            "ticker": "AAPL",
            "price": 228.52,
            "as_of": datetime(2024, 11, 21, tzinfo=timezone.utc),
        }
    )
    yahoo = _FakeYahoo()
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    await service.get_quote("AAPL")
    await service.get_quote("AAPL")
    assert av.quote_calls == 1


async def test_risk_free_rate_fred_primary(cache, isolated_settings):
    fred = _FakeFRED(
        result={
            "rate": 0.0462,
            "as_of": datetime(2024, 11, 20, tzinfo=timezone.utc),
            "source": "FRED",
        }
    )
    service = DataService(
        cache=cache,
        alpha_vantage=None,
        yahoo=_FakeYahoo(),
        fred=fred,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    result = await service.get_risk_free_rate()
    assert result.source == "FRED"
    assert result.rate == pytest.approx(0.0462)


async def test_risk_free_rate_fallback_when_fred_down(cache, isolated_settings):
    fred = _FakeFRED(exc=ProviderUnavailableError("fred", "down"))
    service = DataService(
        cache=cache,
        alpha_vantage=None,
        yahoo=_FakeYahoo(),
        fred=fred,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    result = await service.get_risk_free_rate()
    assert result.source == "FALLBACK"
    assert 0.0 <= result.rate <= 0.2
    assert any("FRED unavailable" in w for w in result.warnings)


async def test_risk_free_rate_fallback_when_no_fred_client(cache, isolated_settings):
    service = DataService(
        cache=cache,
        alpha_vantage=None,
        yahoo=_FakeYahoo(),
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    result = await service.get_risk_free_rate()
    assert result.source == "FALLBACK"


async def test_invalid_ticker_rejected_before_upstream(cache, isolated_settings):
    service = DataService(
        cache=cache,
        alpha_vantage=None,
        yahoo=_FakeYahoo(),
        fred=None,
        use_mock_fallback=True,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    from app.errors import InvalidReturnWindowError

    with pytest.raises(InvalidReturnWindowError):
        await service.get_quote("bad ticker with spaces")


async def test_invalid_lookback_rejected(cache, isolated_settings):
    service = DataService(
        cache=cache,
        alpha_vantage=None,
        yahoo=_FakeYahoo(),
        fred=None,
        use_mock_fallback=True,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    from app.errors import InvalidReturnWindowError

    with pytest.raises(InvalidReturnWindowError):
        await service.get_historical("AAPL", lookback_years=0)
    with pytest.raises(InvalidReturnWindowError):
        await service.get_historical("AAPL", lookback_years=99)
