"""Orchestrates the cache + providers + fallback chain.

DataService is what routes call. It is provider-agnostic and never lets raw
upstream errors leak; everything maps to typed ``AppError`` subclasses. Every
response path also reports which provider was used via a return-side
``source`` field so routes can surface it as the ``X-Data-Source`` response
header.

Fallback order per plan:
    Alpha Vantage  →  Yahoo  →  (opt-in) Mock
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from typing import Any

import pandas as pd

from app.data.cache import MarketCache
from app.data.calendar import last_trading_day_on_or_before
from app.data.clients.alpha_vantage import AlphaVantageClient
from app.data.clients.fred import FredClient
from app.data.clients.yahoo import YahooClient, valuation_fundamentals_bundle_complete
from app.data.mock import (
    PROVIDER_NAME as MOCK_PROVIDER,
)
from app.data.mock import (
    generate_daily_bars,
    generate_quote,
)
from app.errors import (
    InsufficientHistoryError,
    InvalidReturnWindowError,
    ProviderUnavailableError,
    RateLimitError,
    UnknownTickerError,
)
from app.schemas import PriceBar, Quote, ReturnFrequency
from app.settings import FRED_FALLBACK_RATE

logger = logging.getLogger(__name__)

# Minimum observations we consider "enough" to compute 5y-scale metrics
# downstream. 1200 is ~4.76y of daily bars — generous enough to allow short
# listings but catches empty-series bugs fast.
MIN_HISTORICAL_OBSERVATIONS = 30


class HistoricalResult:
    __slots__ = ("bars", "frequency", "source", "ticker", "warnings")

    def __init__(
        self,
        ticker: str,
        frequency: ReturnFrequency,
        bars: list[PriceBar],
        source: str,
        warnings: list[str],
    ) -> None:
        self.ticker = ticker
        self.frequency = frequency
        self.bars = bars
        self.source = source
        self.warnings = warnings


class QuoteResult:
    __slots__ = ("quote", "source", "warnings")

    def __init__(self, quote: Quote, source: str, warnings: list[str]) -> None:
        self.quote = quote
        self.source = source
        self.warnings = warnings


class RiskFreeRateResult:
    __slots__ = ("as_of", "rate", "source", "warnings")

    def __init__(
        self, rate: float, as_of: datetime, source: str, warnings: list[str]
    ) -> None:
        self.rate = rate
        self.as_of = as_of
        self.source = source
        self.warnings = warnings


class DataService:
    def __init__(
        self,
        *,
        cache: MarketCache,
        alpha_vantage: AlphaVantageClient | None,
        yahoo: YahooClient,
        fred: FredClient | None,
        use_mock_fallback: bool,
        quote_ttl_seconds: int,
        risk_free_rate_ttl_seconds: int,
    ) -> None:
        self._cache = cache
        self._av = alpha_vantage
        self._yahoo = yahoo
        self._fred = fred
        self._use_mock = use_mock_fallback
        self._quote_ttl = quote_ttl_seconds
        self._rfr_ttl = risk_free_rate_ttl_seconds

    # ------------------------------------------------------------------
    # Historical
    # ------------------------------------------------------------------

    async def get_historical(
        self,
        ticker: str,
        *,
        frequency: ReturnFrequency = ReturnFrequency.DAILY,
        lookback_years: int = 5,
        as_of: Date | None = None,
    ) -> HistoricalResult:
        ticker = _normalize_ticker(ticker)
        if not (1 <= lookback_years <= 20):
            raise InvalidReturnWindowError(
                "lookbackYears must be between 1 and 20",
                {"lookbackYears": lookback_years},
            )
        # as_of pins the window end. Production API calls leave it None so the
        # anchor tracks "today"; fixture / snapshot tests pass a fixed calendar
        # date (e.g. Dataset B's 2024-11-21) so the window is deterministic.
        anchor = as_of if as_of is not None else datetime.now(UTC).date()
        window_end = last_trading_day_on_or_before(anchor)
        cache_key = f"historical:{ticker}:{frequency.value}:{window_end.isoformat()}:{lookback_years}"

        async def _load() -> HistoricalResult:
            cached = await self._cache.get_historical(
                ticker, frequency.value, window_end, lookback_years
            )
            if cached is not None:
                bars = [PriceBar(**b) for b in cached.payload["bars"]]
                return HistoricalResult(ticker, frequency, bars, cached.source, [])
            return await self._fetch_historical(
                ticker, frequency=frequency, lookback_years=lookback_years, window_end=window_end
            )

        return await self._cache.run_singleflight(cache_key, _load)

    async def _fetch_historical(
        self,
        ticker: str,
        *,
        frequency: ReturnFrequency,
        lookback_years: int,
        window_end: Date,
    ) -> HistoricalResult:
        warnings: list[str] = []
        daily_bars, source = await self._fetch_daily_bars_with_fallback(
            ticker, lookback_years=lookback_years, window_end=window_end, warnings=warnings
        )

        if frequency is ReturnFrequency.DAILY:
            bars_dict = daily_bars
        elif frequency is ReturnFrequency.WEEKLY:
            bars_dict = _resample_bars(daily_bars, "W-FRI")
        elif frequency is ReturnFrequency.MONTHLY:
            bars_dict = _resample_bars(daily_bars, "ME")
        else:  # pragma: no cover — enum exhausted
            raise InvalidReturnWindowError(f"Unsupported frequency: {frequency}")

        if len(bars_dict) < MIN_HISTORICAL_OBSERVATIONS:
            raise InsufficientHistoryError(
                ticker, len(bars_dict), MIN_HISTORICAL_OBSERVATIONS
            )

        bars = [PriceBar(**b) for b in bars_dict]
        payload = {"bars": bars_dict}
        await self._cache.put_historical(
            ticker, frequency.value, window_end, lookback_years, payload, source
        )
        return HistoricalResult(ticker, frequency, bars, source, warnings)

    async def _fetch_daily_bars_with_fallback(
        self,
        ticker: str,
        *,
        lookback_years: int,
        window_end: Date,
        warnings: list[str],
    ) -> tuple[list[dict[str, Any]], str]:
        unknown_from_av = False
        last_error: RateLimitError | ProviderUnavailableError | None = None

        if self._av is not None:
            try:
                bars = await self._av.get_historical_daily(ticker)
                trimmed = _trim_to_window(bars, window_end, lookback_years)
                if not trimmed:
                    raise ProviderUnavailableError(
                        "alpha-vantage", "trimmed bar set is empty"
                    )
                return trimmed, "alpha-vantage"
            except UnknownTickerError:
                unknown_from_av = True
            except RateLimitError as exc:
                logger.warning("alpha_vantage rate limit: %s", exc.message)
                warnings.append("Alpha Vantage rate-limited; used Yahoo fallback")
                last_error = exc
            except ProviderUnavailableError as exc:
                logger.warning("alpha_vantage unavailable: %s", exc.message)
                warnings.append(f"Alpha Vantage unavailable: {exc.message}; used Yahoo fallback")
                last_error = exc

        try:
            bars = await self._yahoo.get_historical_daily(
                ticker, lookback_years=lookback_years, end=window_end
            )
            trimmed = _trim_to_window(bars, window_end, lookback_years)
            if not trimmed:
                raise ProviderUnavailableError("yahoo", "trimmed bar set is empty")
            return trimmed, "yahoo"
        except UnknownTickerError:
            if unknown_from_av:
                raise
            raise UnknownTickerError(ticker) from None
        except (ProviderUnavailableError, RateLimitError) as exc:
            logger.warning("yahoo fallback failed: %s", exc.message)
            warnings.append(f"Yahoo fallback failed: {exc.message}")
            last_error = exc

        if self._use_mock:
            warnings.append("Served mock data (all providers unavailable)")
            bars = generate_daily_bars(ticker, lookback_years=lookback_years, end=window_end)
            if not bars:
                raise ProviderUnavailableError(MOCK_PROVIDER, "mock produced empty series")
            return bars, MOCK_PROVIDER

        if isinstance(last_error, RateLimitError):
            raise last_error
        raise ProviderUnavailableError("all", "Alpha Vantage and Yahoo unavailable")

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    async def get_quote(self, ticker: str) -> QuoteResult:
        ticker = _normalize_ticker(ticker)
        cache_key = f"quote:{ticker}"

        async def _load() -> QuoteResult:
            cached = await self._cache.get_quote(ticker, self._quote_ttl)
            if cached is not None:
                return QuoteResult(
                    Quote(ticker=cached.ticker, price=cached.price, as_of=cached.as_of),
                    cached.source,
                    [],
                )
            return await self._fetch_quote(ticker)

        return await self._cache.run_singleflight(cache_key, _load)

    async def _fetch_quote(self, ticker: str) -> QuoteResult:
        warnings: list[str] = []
        unknown_from_av = False
        last_error: RateLimitError | ProviderUnavailableError | None = None

        if self._av is not None:
            try:
                q = await self._av.get_quote(ticker)
                quote = Quote(ticker=q["ticker"], price=q["price"], as_of=q["as_of"])
                await self._cache.put_quote(ticker, quote.price, quote.as_of, "alpha-vantage")
                return QuoteResult(quote, "alpha-vantage", warnings)
            except UnknownTickerError:
                unknown_from_av = True
            except RateLimitError as exc:
                logger.warning("alpha_vantage quote rate limit: %s", exc.message)
                warnings.append("Alpha Vantage rate-limited; used Yahoo fallback")
                last_error = exc
            except ProviderUnavailableError as exc:
                logger.warning("alpha_vantage quote unavailable: %s", exc.message)
                warnings.append(f"Alpha Vantage unavailable: {exc.message}; used Yahoo fallback")
                last_error = exc

        try:
            q = await self._yahoo.get_quote(ticker)
            quote = Quote(ticker=q["ticker"], price=q["price"], as_of=q["as_of"])
            await self._cache.put_quote(ticker, quote.price, quote.as_of, "yahoo")
            return QuoteResult(quote, "yahoo", warnings)
        except UnknownTickerError:
            if unknown_from_av:
                raise
            raise UnknownTickerError(ticker) from None
        except (ProviderUnavailableError, RateLimitError) as exc:
            logger.warning("yahoo quote fallback failed: %s", exc.message)
            warnings.append(f"Yahoo fallback failed: {exc.message}")
            last_error = exc

        if self._use_mock:
            warnings.append("Served mock quote (all providers unavailable)")
            q = generate_quote(ticker)
            quote = Quote(ticker=q["ticker"], price=q["price"], as_of=q["as_of"])
            await self._cache.put_quote(ticker, quote.price, quote.as_of, MOCK_PROVIDER)
            return QuoteResult(quote, MOCK_PROVIDER, warnings)

        if isinstance(last_error, RateLimitError):
            raise last_error
        raise ProviderUnavailableError("all", "Alpha Vantage and Yahoo unavailable")

    # ------------------------------------------------------------------
    # Risk-free rate
    # ------------------------------------------------------------------

    async def get_risk_free_rate(self) -> RiskFreeRateResult:
        cache_key = "rfr:latest"

        async def _load() -> RiskFreeRateResult:
            cached = await self._cache.get_risk_free_rate(self._rfr_ttl)
            if cached is not None:
                return RiskFreeRateResult(cached.rate, cached.as_of, cached.source, [])
            return await self._fetch_risk_free_rate()

        return await self._cache.run_singleflight(cache_key, _load)

    async def _fetch_risk_free_rate(self) -> RiskFreeRateResult:
        warnings: list[str] = []
        if self._fred is not None:
            try:
                payload = await self._fred.get_latest_dgs3mo()
                await self._cache.put_risk_free_rate(
                    payload["rate"], payload["as_of"], payload["source"]
                )
                return RiskFreeRateResult(
                    payload["rate"], payload["as_of"], payload["source"], warnings
                )
            except ProviderUnavailableError as exc:
                logger.warning("FRED unavailable: %s", exc.message)
                warnings.append(f"FRED unavailable: {exc.message}; using static fallback")

        fallback_as_of = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        await self._cache.put_risk_free_rate(FRED_FALLBACK_RATE, fallback_as_of, "FALLBACK")
        return RiskFreeRateResult(FRED_FALLBACK_RATE, fallback_as_of, "FALLBACK", warnings)

    # ------------------------------------------------------------------
    # Fundamentals for valuation (Yahoo first, Alpha Vantage fallback)
    # ------------------------------------------------------------------

    async def get_fundamentals_bundle_for_valuation(
        self, ticker: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
        """Return income, balance, cashflow, overview (Alpha-Vantage-shaped) + provider id."""

        ticker = _normalize_ticker(ticker)
        kinds = ("income", "balance", "cashflow", "overview")
        entries = [await self._cache.get_fundamentals_with_source(ticker, k) for k in kinds]
        if all(e is not None for e in entries):
            inc, src0 = entries[0]  # type: ignore[misc]
            bal, src1 = entries[1]  # type: ignore[misc]
            cf, src2 = entries[2]  # type: ignore[misc]
            ov, src3 = entries[3]  # type: ignore[misc]
            srcs = {src0, src1, src2, src3}
            if (
                len(srcs) == 1
                and valuation_fundamentals_bundle_complete(inc, bal, cf, ov)
            ):
                return inc, bal, cf, ov, src0

        key = f"fundamentals_bundle_valuation:{ticker}"

        async def _load() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
            yahoo_exc: UnknownTickerError | ProviderUnavailableError | None = None
            try:
                inc, bal, cf, ov = await self._yahoo.get_fundamentals_bundle_for_valuation(
                    ticker
                )
            except (UnknownTickerError, ProviderUnavailableError) as exc:
                yahoo_exc = exc
            else:
                await self._cache.put_fundamentals(ticker, "income", inc, "yahoo")
                await self._cache.put_fundamentals(ticker, "balance", bal, "yahoo")
                await self._cache.put_fundamentals(ticker, "cashflow", cf, "yahoo")
                await self._cache.put_fundamentals(ticker, "overview", ov, "yahoo")
                return inc, bal, cf, ov, "yahoo"

            if self._av is None:
                assert yahoo_exc is not None
                raise yahoo_exc

            inc = await self._av.get_income_statement(ticker)
            bal = await self._av.get_balance_sheet(ticker)
            cf = await self._av.get_cash_flow(ticker)
            ov = await self._av.get_overview(ticker)
            await self._cache.put_fundamentals(ticker, "income", inc, "alpha-vantage")
            await self._cache.put_fundamentals(ticker, "balance", bal, "alpha-vantage")
            await self._cache.put_fundamentals(ticker, "cashflow", cf, "alpha-vantage")
            await self._cache.put_fundamentals(ticker, "overview", ov, "alpha-vantage")
            return inc, bal, cf, ov, "alpha-vantage"

        return await self._cache.run_singleflight(key, _load)


_TICKER_RE = re.compile(r"[A-Z0-9.]{1,10}")


def _normalize_ticker(raw: str) -> str:
    if not raw:
        raise InvalidReturnWindowError("ticker is required")
    value = raw.strip().upper()
    if not _TICKER_RE.fullmatch(value):
        raise InvalidReturnWindowError(
            f"invalid ticker: {raw!r}", {"ticker": raw}
        )
    return value


def _trim_to_window(
    bars: list[dict[str, Any]],
    window_end: Date,
    lookback_years: int,
) -> list[dict[str, Any]]:
    if not bars:
        return []
    window_start = window_end - timedelta(days=int(lookback_years * 366))
    start_iso = window_start.isoformat()
    end_iso = window_end.isoformat()
    return [b for b in bars if start_iso <= b["date"] <= end_iso]


def _resample_bars(daily: list[dict[str, Any]], rule: str) -> list[dict[str, Any]]:
    if not daily:
        return []
    frame = pd.DataFrame(daily)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    agg = frame.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    agg = agg.dropna(subset=["open", "high", "low", "close"])
    result: list[dict[str, Any]] = []
    for idx, row in agg.iterrows():
        result.append(
            {
                "date": idx.date().isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
            }
        )
    return result


__all__ = [
    "DataService",
    "HistoricalResult",
    "QuoteResult",
    "RiskFreeRateResult",
]
