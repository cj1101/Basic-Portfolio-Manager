"""ValuationService with mocked fundamentals."""

from __future__ import annotations

from datetime import date as Date
from unittest.mock import AsyncMock

import pytest

from app.data.calendar import last_trading_day_on_or_before
from app.data.service import HistoricalResult
from app.schemas import PriceBar, ReturnFrequency, ValuationRequest
from app.services.valuation_service import ValuationService

pytestmark = pytest.mark.asyncio


def _fake_monthly_hist(ticker: str) -> HistoricalResult:
    bars: list[PriceBar] = []
    y, m = 2018, 1
    for _ in range(40):
        bars.append(
            PriceBar(
                date=Date(y, m, 1),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1_000_000,
            )
        )
        m += 1
        if m > 12:
            m = 1
            y += 1
    return HistoricalResult(ticker, ReturnFrequency.MONTHLY, bars, "mock", [])


def _minimal_fundamentals(*, ebit: str = "100000", revenue: str = "400000") -> AsyncMock:
    ds = AsyncMock()
    inc = {
        "annualReports": [
            {
                "ebit": ebit,
                "incomeBeforeTax": "120000",
                "incomeTaxExpense": "25000",
                "interestExpense": "5000",
                "totalRevenue": revenue,
            },
            {
                "ebit": ebit,
                "incomeBeforeTax": "120000",
                "incomeTaxExpense": "25000",
                "interestExpense": "5000",
                "totalRevenue": revenue,
            },
        ]
    }
    bal = {
        "annualReports": [
            {
                "totalCurrentAssets": "150000",
                "totalCurrentLiabilities": "130000",
                "totalDebt": "80000",
                "cashAndCashEquivalentsAtCarryingValue": "30000",
            },
            {
                "totalCurrentAssets": "140000",
                "totalCurrentLiabilities": "125000",
                "totalDebt": "78000",
                "cashAndCashEquivalentsAtCarryingValue": "28000",
            },
        ]
    }
    cf = {
        "annualReports": [
            {
                "capitalExpenditures": "-12000",
                "depreciationDepletionAndAmortization": "11000",
            }
        ]
    }
    ov = {
        "Symbol": "FAKE",
        "Sector": "TECHNOLOGY",
        "Industry": "SEMICONDUCTORS",
        "Beta": "1.2",
        "SharesOutstanding": "10000",
        "DividendPerShare": "0.5",
        "DividendYield": "0.002",
    }
    ds.get_fundamentals_bundle_for_valuation.return_value = (inc, bal, cf, ov, "yahoo")
    ds.get_historical = AsyncMock(
        side_effect=lambda ticker, **kwargs: _fake_monthly_hist(ticker)
    )
    return ds


async def test_bank_ticker_omits_ebit_fcff() -> None:
    ds = _minimal_fundamentals()
    inc, bal, cf, _prev_ov, prov = ds.get_fundamentals_bundle_for_valuation.return_value
    ov_jpm = {
        "Symbol": "JPM",
        "Sector": "",
        "Industry": "",
        "Beta": "1.0",
        "SharesOutstanding": "3000000",
        "DividendPerShare": "4",
    }
    ds.get_fundamentals_bundle_for_valuation.return_value = (inc, bal, cf, ov_jpm, prov)
    req = ValuationRequest(
        tickers=["JPM"],
        wacc=0.09,
        fcff_growth=0.02,
        fcff_terminal_growth=0.02,
        ddm_gordon_g=0.03,
    )
    res, _ = await ValuationService().run(req, data_service=ds, risk_free_rate=0.04)
    row = res.per_ticker[0]
    assert row.ticker == "JPM"
    assert row.fcff is None
    assert row.fcfe is None
    assert any("not reliable" in w.lower() for w in row.warnings)


async def test_industrial_computes_fcff_fcfe() -> None:
    ds = _minimal_fundamentals()
    req = ValuationRequest(
        tickers=["FAKE"],
        wacc=0.09,
        fcff_growth=0.02,
        fcff_terminal_growth=0.02,
        ddm_gordon_g=0.03,
    )
    res, _ = await ValuationService().run(req, data_service=ds, risk_free_rate=0.04)
    row = res.per_ticker[0]
    assert row.fcff is not None
    assert row.fcfe is not None
    assert row.fcff_value_per_share is not None


async def test_as_of_passed_to_historical_and_sets_result_timestamp() -> None:
    ds = _minimal_fundamentals()
    anchor = Date(2020, 6, 15)

    async def _hist_side_effect(ticker: str, **kwargs: object) -> HistoricalResult:
        assert kwargs.get("as_of") == anchor
        return _fake_monthly_hist(ticker)

    ds.get_historical = AsyncMock(side_effect=_hist_side_effect)
    req = ValuationRequest(
        tickers=["FAKE"],
        as_of=anchor,
        wacc=0.09,
        fcff_growth=0.02,
        fcff_terminal_growth=0.02,
        ddm_gordon_g=0.03,
    )
    res, _ = await ValuationService().run(req, data_service=ds, risk_free_rate=0.04)
    assert res.as_of.date() == last_trading_day_on_or_before(anchor)
    ds.get_historical.assert_awaited()
    assert ds.get_historical.await_args_list[0].kwargs.get("as_of") == anchor
