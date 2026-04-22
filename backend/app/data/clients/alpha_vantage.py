"""Alpha Vantage client — the ONLY module allowed to call api.alphavantage.co.

Owns the rate limiter (SPEC §9). Re-maps every upstream failure mode to a typed
``AppError`` so raw upstream bodies never reach clients.

Supported endpoints:

* ``TIME_SERIES_DAILY_ADJUSTED``  — historical daily OHLCV + adjusted close.
* ``GLOBAL_QUOTE``                — latest price snapshot.
* ``INCOME_STATEMENT``, ``BALANCE_SHEET``, ``CASH_FLOW`` — company fundamentals.
* ``OVERVIEW``                    — high-level ratios and `SharesOutstanding` / dividends.

Alpha Vantage returns HTTP 200 for soft rate-limit / quota violations with a
``Note`` or ``Information`` string in the JSON body. We detect these and
remap to ``RateLimitError``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from datetime import date as Date
from typing import Any

import httpx

from app.data.rate_limit import AlphaVantageRateLimiter
from app.errors import (
    ProviderUnavailableError,
    RateLimitError,
    UnknownTickerError,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "alpha-vantage"


class AlphaVantageClient:
    def __init__(
        self,
        *,
        api_key: str,
        rate_limiter: AlphaVantageRateLimiter,
        base_url: str = "https://www.alphavantage.co/query",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._rate_limiter = rate_limiter
        self._base_url = base_url
        self._timeout = timeout
        self._http_client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> AlphaVantageClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def close(self) -> None:
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def _get(self, params: dict[str, str]) -> dict[str, Any]:
        await self._rate_limiter.acquire()
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        full_params = {**params, "apikey": self._api_key}
        try:
            resp = await self._http_client.get(self._base_url, params=full_params)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, "timeout") from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, str(exc)) from exc

        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            raise RateLimitError(PROVIDER_NAME, retry_after or 60.0, scope="minute")
        if resp.status_code >= 500:
            raise ProviderUnavailableError(
                PROVIDER_NAME, f"upstream {resp.status_code}"
            )
        if resp.status_code >= 400:
            raise ProviderUnavailableError(
                PROVIDER_NAME, f"unexpected status {resp.status_code}"
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, "invalid JSON") from exc

        _check_soft_errors(payload)
        return payload

    async def get_historical_daily(
        self,
        ticker: str,
        *,
        outputsize: str = "full",
    ) -> list[dict[str, Any]]:
        """Return a list of bar dicts sorted ascending by date.

        Each bar: ``{"date": "YYYY-MM-DD", "open": float, "high": float,
        "low": float, "close": float, "volume": int}``.
        ``close`` is the *adjusted* close per CONTRACTS.md §3.
        """

        payload = await self._get(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker,
                "outputsize": outputsize,
                "datatype": "json",
            }
        )
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict) or not series:
            raise UnknownTickerError(ticker)
        bars: list[dict[str, Any]] = []
        for day, row in series.items():
            try:
                bars.append(
                    {
                        "date": day,
                        "open": float(row["1. open"]),
                        "high": float(row["2. high"]),
                        "low": float(row["3. low"]),
                        "close": float(row["5. adjusted close"]),
                        "volume": int(float(row["6. volume"])),
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderUnavailableError(
                    PROVIDER_NAME, f"malformed bar for {ticker} {day}: {exc}"
                ) from exc
        bars.sort(key=lambda b: b["date"])
        return bars

    async def get_quote(self, ticker: str) -> dict[str, Any]:
        """Return ``{"ticker": str, "price": float, "asOf": datetime}``."""

        payload = await self._get({"function": "GLOBAL_QUOTE", "symbol": ticker})
        block = payload.get("Global Quote")
        if not isinstance(block, dict) or not block or not block.get("05. price"):
            raise UnknownTickerError(ticker)
        try:
            price = float(block["05. price"])
            as_of_raw = block.get("07. latest trading day") or datetime.now(UTC).date().isoformat()
            as_of = _to_utc_datetime(as_of_raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailableError(
                PROVIDER_NAME, f"malformed quote for {ticker}"
            ) from exc
        return {"ticker": ticker, "price": price, "as_of": as_of}

    async def get_income_statement(self, ticker: str) -> dict[str, Any]:
        payload = await self._get(
            {
                "function": "INCOME_STATEMENT",
                "symbol": ticker,
                "datatype": "json",
            }
        )
        if not payload.get("annualReports"):
            raise UnknownTickerError(ticker)
        return payload

    async def get_balance_sheet(self, ticker: str) -> dict[str, Any]:
        payload = await self._get(
            {
                "function": "BALANCE_SHEET",
                "symbol": ticker,
                "datatype": "json",
            }
        )
        if not payload.get("annualReports"):
            raise UnknownTickerError(ticker)
        return payload

    async def get_cash_flow(self, ticker: str) -> dict[str, Any]:
        payload = await self._get(
            {
                "function": "CASH_FLOW",
                "symbol": ticker,
                "datatype": "json",
            }
        )
        if not payload.get("annualReports"):
            raise UnknownTickerError(ticker)
        return payload

    async def get_overview(self, ticker: str) -> dict[str, Any]:
        payload = await self._get(
            {
                "function": "OVERVIEW",
                "symbol": ticker,
                "datatype": "json",
            }
        )
        if not payload.get("Symbol"):
            raise UnknownTickerError(ticker)
        return payload


def _check_soft_errors(payload: dict[str, Any]) -> None:
    """Alpha Vantage returns 200 with an error string on quota / bad symbol."""

    error_msg = payload.get("Error Message")
    if error_msg:
        # AV's classic "Invalid API call" = unknown symbol.
        raise UnknownTickerError(_extract_symbol(payload) or error_msg)

    note = payload.get("Note") or payload.get("Information")
    if note:
        lowered = note.lower()
        # AV often mentions "premium" in the same Note as free-tier throttling; classify
        # rate-limit language first so we return 429 + Retry-After instead of 503.
        rate_limited = (
            "thank you for using" in lowered
            or "api rate limit" in lowered
            or "requests per minute" in lowered
            or "requests per day" in lowered
            or "sparingly" in lowered
        )
        if rate_limited:
            raise RateLimitError(PROVIDER_NAME, 1.2, scope="minute")
        if "premium" in lowered or "higher" in lowered or "api key" in lowered:
            raise ProviderUnavailableError(PROVIDER_NAME, note)
        raise ProviderUnavailableError(PROVIDER_NAME, note)


def _extract_symbol(payload: dict[str, Any]) -> str | None:
    meta = payload.get("Meta Data")
    if isinstance(meta, dict):
        for key, value in meta.items():
            if "Symbol" in key and isinstance(value, str):
                return value
    return None


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_utc_datetime(value: str) -> datetime:
    try:
        if len(value) == 10:
            d = Date.fromisoformat(value)
            return datetime.combine(d, datetime.min.time(), tzinfo=UTC)
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return datetime.now(UTC)


__all__ = ["PROVIDER_NAME", "AlphaVantageClient"]
