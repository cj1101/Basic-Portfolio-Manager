"""Yahoo → Alpha-Vantage-shaped fundamentals normalization (no network)."""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.clients.yahoo import (
    av_annual_reports_from_statement_frame,
    fundamentals_bundle_from_frames,
    overview_dict_from_yfinance_info,
    valuation_fundamentals_bundle_complete,
    _balance_row_to_av_key,
    _income_row_to_av_key,
)
from app.errors import ProviderUnavailableError, UnknownTickerError


def test_income_row_mapping() -> None:
    assert _income_row_to_av_key("Total Revenue") == "totalRevenue"
    assert _income_row_to_av_key("EBIT") == "ebit"
    assert _income_row_to_av_key("Operating Income") == "ebit"
    assert _income_row_to_av_key("Tax Provision") == "incomeTaxExpense"
    assert _income_row_to_av_key("Cost Of Revenue") is None


def test_balance_row_mapping() -> None:
    assert _balance_row_to_av_key("Total Debt") == "totalDebt"
    assert _balance_row_to_av_key("Current Assets") == "totalCurrentAssets"


def test_av_annual_reports_from_frame_newest_first() -> None:
    frame = pd.DataFrame(
        [[100.0, 120.0], [10.0, 15.0]],
        index=["Total Revenue", "EBIT"],
        columns=pd.to_datetime(["2022-12-31", "2023-12-31"]),
    )
    reports = av_annual_reports_from_statement_frame(frame, _income_row_to_av_key)
    assert len(reports) == 2
    assert reports[0]["totalRevenue"] == "120"
    assert reports[0]["ebit"] == "15"
    assert reports[1]["totalRevenue"] == "100"


def test_overview_from_info() -> None:
    ov = overview_dict_from_yfinance_info(
        {
            "symbol": "xyz",
            "sector": "Technology",
            "industry": "Software",
            "beta": 1.1,
            "sharesOutstanding": 1_000_000_000,
            "dividendRate": 0.24,
            "dividendYield": 0.005,
        },
        "XYZ",
    )
    assert ov["Symbol"] == "XYZ"
    assert ov["Sector"] == "Technology"
    assert ov["Beta"] == "1.1"
    assert ov["SharesOutstanding"] == "1000000000"
    assert ov["DividendPerShare"] == "0.24"
    assert ov["DividendYield"] == "0.005"


def test_fundamentals_bundle_from_frames_complete() -> None:
    y2023 = pd.Timestamp("2023-12-31")
    fin = pd.DataFrame(
        [[400_000], [100_000]],
        index=["Total Revenue", "EBIT"],
        columns=[y2023],
    )
    bal = pd.DataFrame(
        [[150_000], [130_000], [80_000], [30_000]],
        index=[
            "Total Current Assets",
            "Total Current Liabilities",
            "Total Debt",
            "Cash And Cash Equivalents",
        ],
        columns=[y2023],
    )
    cf = pd.DataFrame(
        [[-12_000], [11_000]],
        index=["Capital Expenditure", "Depreciation And Amortization"],
        columns=[y2023],
    )
    info = {"symbol": "FAKE", "sector": "Technology", "industry": "Software", "beta": 1.0}
    inc, b, c, ov = fundamentals_bundle_from_frames(fin, bal, cf, info, "FAKE")
    assert valuation_fundamentals_bundle_complete(inc, b, c, ov)
    assert inc["annualReports"][0]["ebit"] == "100000"
    assert ov["Symbol"] == "FAKE"


def test_fundamentals_bundle_unknown_ticker() -> None:
    with pytest.raises(UnknownTickerError):
        fundamentals_bundle_from_frames(None, None, None, {}, "ZZZZZZ")


def test_fundamentals_bundle_incomplete() -> None:
    y2023 = pd.Timestamp("2023-12-31")
    fin = pd.DataFrame({y2023: {"Total Revenue": 1}}).T
    with pytest.raises(ProviderUnavailableError):
        fundamentals_bundle_from_frames(fin, None, None, {"symbol": "x"}, "X")
