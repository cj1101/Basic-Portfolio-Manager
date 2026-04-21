"""Yahoo Finance fallback via ``yfinance``.

This client is **only** invoked by ``DataService`` when Alpha Vantage is
unavailable. ``yfinance`` uses an unofficial Yahoo endpoint, so we contain
every synchronous call inside ``asyncio.to_thread`` and treat it as best-effort
with generous error handling.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from typing import Any

import pandas as pd

from app.errors import ProviderUnavailableError, UnknownTickerError

logger = logging.getLogger(__name__)

PROVIDER_NAME = "yahoo"


class YahooClient:
    """Fallback-only wrapper around yfinance."""

    def __init__(self, ticker_factory: Any | None = None) -> None:
        # Lazy import: yfinance is relatively heavy and rarely needed.
        self._ticker_factory = ticker_factory

    def _factory(self) -> Any:
        if self._ticker_factory is not None:
            return self._ticker_factory
        import yfinance

        return yfinance.Ticker

    async def get_historical_daily(
        self,
        ticker: str,
        *,
        lookback_years: int,
        end: Date | None = None,
    ) -> list[dict[str, Any]]:
        end_date = end or datetime.now(UTC).date()
        start_date = end_date - timedelta(days=lookback_years * 366)

        def _fetch() -> pd.DataFrame:
            factory = self._factory()
            try:
                t = factory(ticker)
                frame = t.history(
                    start=start_date.isoformat(),
                    end=(end_date + timedelta(days=1)).isoformat(),
                    interval="1d",
                    auto_adjust=True,
                    actions=False,
                    raise_errors=False,
                )
            except Exception as exc:
                raise ProviderUnavailableError(PROVIDER_NAME, str(exc)) from exc
            return frame

        try:
            frame = await asyncio.to_thread(_fetch)
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, str(exc)) from exc

        if frame is None or frame.empty:
            raise UnknownTickerError(ticker)

        bars: list[dict[str, Any]] = []
        for idx, row in frame.iterrows():
            try:
                day = idx.date() if hasattr(idx, "date") else pd.Timestamp(idx).date()
                bars.append(
                    {
                        "date": day.isoformat(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row.get("Volume", 0) or 0),
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderUnavailableError(
                    PROVIDER_NAME, f"malformed row for {ticker}: {exc}"
                ) from exc
        bars.sort(key=lambda b: b["date"])
        if not bars:
            raise UnknownTickerError(ticker)
        return bars

    async def get_quote(self, ticker: str) -> dict[str, Any]:
        def _fetch() -> dict[str, Any]:
            factory = self._factory()
            try:
                t = factory(ticker)
                frame = t.history(period="5d", interval="1d", auto_adjust=True, actions=False)
            except Exception as exc:
                raise ProviderUnavailableError(PROVIDER_NAME, str(exc)) from exc
            if frame is None or frame.empty:
                raise UnknownTickerError(ticker)
            last = frame.iloc[-1]
            idx = frame.index[-1]
            day = idx.date() if hasattr(idx, "date") else pd.Timestamp(idx).date()
            price = float(last["Close"])
            return {
                "ticker": ticker,
                "price": price,
                "as_of": datetime.combine(day, datetime.min.time(), tzinfo=UTC),
            }

        try:
            return await asyncio.to_thread(_fetch)
        except (ProviderUnavailableError, UnknownTickerError):
            raise
        except Exception as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, str(exc)) from exc

    async def close(self) -> None:
        return None


__all__ = ["PROVIDER_NAME", "YahooClient"]
