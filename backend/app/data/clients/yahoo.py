"""Yahoo Finance fallback via ``yfinance``.

This client is invoked by ``DataService`` when Alpha Vantage is unavailable for
prices/history, and as the **primary** source for valuation fundamentals
(annual statements + ``info``), with Alpha Vantage as an optional fallback.

``yfinance`` uses an unofficial Yahoo endpoint, so we contain every synchronous
call inside ``asyncio.to_thread`` and treat it as best-effort with generous
error handling.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from typing import Any

import pandas as pd

from app.errors import ProviderUnavailableError, UnknownTickerError

PROVIDER_NAME = "yahoo"


def _norm_label(label: str) -> str:
    s = str(label).strip().lower().replace(",", " ")
    return " ".join(s.split())


def _to_av_str(val: Any) -> str:
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, (int, float)):
        x = float(val)
        if not math.isfinite(x):
            return "0"
        if x.is_integer():
            return str(int(x))
        return str(x)
    return str(val)


def _sorted_columns_desc(frame: pd.DataFrame) -> list[Any]:
    cols = list(frame.columns)

    def sort_key(c: Any) -> float:
        try:
            return float(pd.Timestamp(c).value)
        except (TypeError, ValueError, OverflowError):
            return 0.0

    return sorted(cols, key=sort_key, reverse=True)


def _income_row_to_av_key(label: str) -> str | None:
    n = _norm_label(label)
    if "cost of revenue" in n or "cost of sales" in n:
        return None
    if "total revenue" in n or n.endswith(" total revenue"):
        return "totalRevenue"
    if n == "net sales":
        return "totalRevenue"
    if n == "revenue":
        return "totalRevenue"
    if "operating revenue" in n and "cost" not in n:
        return "totalRevenue"
    if "tax provision" in n or "income tax expense" in n or n.endswith(" tax expense"):
        return "incomeTaxExpense"
    if "interest expense" in n or "interest paid" in n or "interest and debt expense" in n:
        return "interestExpense"
    if (
        "pretax income" in n
        or "income before tax" in n
        or "earnings before tax" in n
        or n == "income before income taxes"
    ):
        return "incomeBeforeTax"
    if n == "ebit":
        return "ebit"
    if "earnings before interest and taxes" in n:
        return "ebit"
    if n == "operating income" or n.startswith("operating income"):
        return "ebit"
    return None


def _balance_row_to_av_key(label: str) -> str | None:
    n = _norm_label(label)
    if n in ("cash and cash equivalents",) or "cash and cash equivalents" in n:
        return "cashAndCashEquivalentsAtCarryingValue"
    if "cash cash equivalents and short term investments" in n:
        return "cashAndCashEquivalentsAtCarryingValue"
    if n == "total current assets" or n == "current assets":
        return "totalCurrentAssets"
    if n == "total current liabilities" or n == "current liabilities":
        return "totalCurrentLiabilities"
    if n == "total debt" or n.endswith(" total debt"):
        return "totalDebt"
    if "current debt" in n or n == "short long term debt" or n == "short term debt":
        return "shortTermDebt"
    if "long term debt" in n and "non" not in n[:20]:
        return "longTermDebt"
    return None


def _cashflow_row_to_av_key(label: str) -> str | None:
    n = _norm_label(label)
    if "capital expenditure" in n or ("purchase of" in n and "ppe" in n):
        return "capitalExpenditures"
    if "purchase of property plant" in n:
        return "capitalExpenditures"
    if (
        ("depreciation" in n and "amortization" in n)
        or n == "reconciled depreciation"
        or "depreciation and amortization" in n
    ):
        return "depreciationDepletionAndAmortization"
    if n == "depreciation" or n.endswith(" depreciation"):
        return "depreciationDepletionAndAmortization"
    return None


def av_annual_reports_from_statement_frame(
    frame: pd.DataFrame | None,
    row_mapper: Callable[[str], str | None],
) -> list[dict[str, str]]:
    """Map a yfinance annual statement DataFrame to Alpha-Vantage-shaped rows."""

    if frame is None or frame.empty:
        return []
    cols = _sorted_columns_desc(frame)
    reports: list[dict[str, str]] = []
    for col in cols:
        row_dict: dict[str, str] = {}
        for idx in frame.index:
            av_key = row_mapper(str(idx))
            if not av_key:
                continue
            try:
                val = frame.at[idx, col]
            except (KeyError, TypeError):
                continue
            if pd.isna(val):
                continue
            if av_key not in row_dict:
                row_dict[av_key] = _to_av_str(val)
        if row_dict:
            reports.append(row_dict)
    return reports


def overview_dict_from_yfinance_info(info: dict[str, Any], ticker: str) -> dict[str, Any]:
    """Map ``Ticker.info`` into keys ``ValuationService`` / eligibility already read."""

    out: dict[str, Any] = {}
    sym = info.get("symbol") or ticker
    out["Symbol"] = str(sym).upper().strip()
    if info.get("sector"):
        out["Sector"] = str(info["sector"])
    if info.get("industry"):
        out["Industry"] = str(info["industry"])
    name = info.get("longName") or info.get("shortName") or info.get("name")
    if name:
        out["Name"] = str(name)
    beta = info.get("beta")
    if beta is not None:
        try:
            out["Beta"] = str(float(beta))
        except (TypeError, ValueError):
            pass
    sh = info.get("sharesOutstanding")
    if sh is not None:
        try:
            out["SharesOutstanding"] = str(int(float(sh)))
        except (TypeError, ValueError):
            pass
    dps = info.get("dividendRate")
    if dps is None:
        dps = info.get("trailingAnnualDividendRate")
    if dps is not None:
        try:
            out["DividendPerShare"] = str(float(dps))
        except (TypeError, ValueError):
            pass
    dy = info.get("dividendYield")
    if dy is None:
        dy = info.get("trailingAnnualDividendYield")
    if dy is not None:
        try:
            out["DividendYield"] = str(float(dy))
        except (TypeError, ValueError):
            pass
    return out


def valuation_fundamentals_bundle_complete(
    inc: dict[str, Any],
    bal: dict[str, Any],
    cf: dict[str, Any],
    ov: dict[str, Any],
) -> bool:
    """Return True if the four blobs can feed ``ValuationService``."""

    def _ok_reports(d: dict[str, Any]) -> bool:
        r = d.get("annualReports")
        return isinstance(r, list) and len(r) > 0

    if not (_ok_reports(inc) and _ok_reports(bal) and _ok_reports(cf)):
        return False
    if not ov.get("Symbol"):
        return False
    return True


def fundamentals_bundle_from_frames(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    info: dict[str, Any],
    ticker: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build AV-shaped income/balance/cashflow/overview dicts from yfinance objects."""

    inc = {"annualReports": av_annual_reports_from_statement_frame(financials, _income_row_to_av_key)}
    bal = {"annualReports": av_annual_reports_from_statement_frame(balance_sheet, _balance_row_to_av_key)}
    cf = {"annualReports": av_annual_reports_from_statement_frame(cashflow, _cashflow_row_to_av_key)}
    ov = overview_dict_from_yfinance_info(info, ticker)

    all_empty = (
        (financials is None or financials.empty)
        and (balance_sheet is None or balance_sheet.empty)
        and (cashflow is None or cashflow.empty)
        and not info
    )
    if all_empty:
        raise UnknownTickerError(ticker)
    if not valuation_fundamentals_bundle_complete(inc, bal, cf, ov):
        raise ProviderUnavailableError(
            PROVIDER_NAME, f"incomplete fundamentals from Yahoo for {ticker}"
        )
    return inc, bal, cf, ov


class YahooClient:
    """Wrapper around yfinance for quotes, history, and valuation fundamentals."""

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

    async def get_fundamentals_bundle_for_valuation(
        self, ticker: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Annual statements + overview in Alpha-Vantage JSON shape for ``ValuationService``."""

        def _fetch() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
            factory = self._factory()
            try:
                t = factory(ticker)
            except Exception as exc:
                raise ProviderUnavailableError(PROVIDER_NAME, str(exc)) from exc
            fin = getattr(t, "financials", None)
            bal = getattr(t, "balance_sheet", None)
            cf = getattr(t, "cashflow", None)
            try:
                raw_info = t.info
            except Exception:
                raw_info = None
            info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
            return fundamentals_bundle_from_frames(fin, bal, cf, info, ticker)

        try:
            return await asyncio.to_thread(_fetch)
        except (UnknownTickerError, ProviderUnavailableError):
            raise
        except Exception as exc:
            raise ProviderUnavailableError(PROVIDER_NAME, str(exc)) from exc

    async def close(self) -> None:
        return None


__all__ = [
    "PROVIDER_NAME",
    "YahooClient",
    "av_annual_reports_from_statement_frame",
    "fundamentals_bundle_from_frames",
    "overview_dict_from_yfinance_info",
    "valuation_fundamentals_bundle_complete",
]
