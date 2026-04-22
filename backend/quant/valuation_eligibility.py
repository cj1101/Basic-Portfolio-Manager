"""Heuristics for when EBIT+ΔNWC FCFF is not meaningful (banks, insurers, etc.)."""

from __future__ import annotations

from typing import Any

# Deposit-taking and broker-dealer names where working-capital FCFF is structurally wrong.
_KNOWN_FINANCIAL_TICKERS = frozenset(
    {
        "JPM",
        "BAC",
        "WFC",
        "C",
        "USB",
        "PNC",
        "TFC",
        "BK",
        "STT",
        "NTRS",
        "FITB",
        "RF",
        "CFG",
        "HBAN",
        "KEY",
        "MTB",
        "CMA",
        "ZION",
        "WAL",
        "GS",
        "MS",
        "SCHW",
        "RJF",
        "BLK",
        "TROW",
        "BEN",
        "IVZ",
        "AMP",
        "MET",
        "PRU",
        "AIG",
        "ALL",
        "TRV",
        "PGR",
        "AFL",
        "LNC",
        "GL",
        "AON",
        "MMC",
        "AJG",
        "BRO",
        "WRB",
        "CB",
        "AXP",
        "COF",
        "DFS",
        "SYF",
        "ALLY",
    }
)

_INDUSTRY_NEEDLES = (
    "FINANCIAL",
    "BANK",
    "INSURANCE",
    "CAPITAL MARKETS",
    "ASSET MANAGEMENT",
    "CREDIT SERVICES",
    "MORTGAGE",
    "THRIFT",
    "SAVINGS",
    "REGIONAL",
)


def _first_float(d: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        v = d.get(k)
        if v is None or v == "None" or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _overview_blob(overview: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("Sector", "sector", "Industry", "industry", "Name", "name"):
        v = overview.get(key)
        if v is not None and str(v).strip():
            parts.append(str(v))
    return " ".join(parts).upper()


def skip_ebit_based_fcff(
    ticker: str,
    overview: dict[str, Any],
    income_latest: dict[str, Any],
    balance_latest: dict[str, Any],
) -> bool:
    """Return True if EBIT-based FCFF / FCFE from statements should be omitted."""
    t = str(ticker).upper().strip()
    if t in _KNOWN_FINANCIAL_TICKERS:
        return True
    blob = _overview_blob(overview)
    if any(n in blob for n in _INDUSTRY_NEEDLES):
        return True
    rev = _first_float(income_latest, "totalRevenue", "revenue")
    cl = _first_float(
        balance_latest, "totalCurrentLiabilities", "currentLiabilities"
    )
    if rev is not None and rev > 0 and cl is not None and cl / rev > 4.5:
        return True
    return False


__all__ = ["skip_ebit_based_fcff"]
