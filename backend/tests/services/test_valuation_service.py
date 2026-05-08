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
    price = 100.0
    for _ in range(40):
        bars.append(
            PriceBar(
                date=Date(y, m, 1),
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price,
                close_nominal=price,
                volume=1_000_000,
            )
        )
        price += 1.0
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
                "netIncome": "90000",
                "dilutedEPS": "2.0",
            },
            {
                "ebit": ebit,
                "incomeBeforeTax": "120000",
                "incomeTaxExpense": "25000",
                "interestExpense": "5000",
                "totalRevenue": revenue,
                "netIncome": "90000",
                "dilutedEPS": "2.0",
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
                "totalStockholderEquity": "900000",
                "totalAssets": "1500000",
            },
            {
                "totalCurrentAssets": "140000",
                "totalCurrentLiabilities": "125000",
                "totalDebt": "78000",
                "cashAndCashEquivalentsAtCarryingValue": "28000",
                "totalStockholderEquity": "840000",
                "totalAssets": "1450000",
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
        "MarketCapitalization": "2000000",
        "returnOnEquity": "0.10",
        "payoutRatio": "0.25",
        "earningsGrowth": "0.08",
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
    req = ValuationRequest(tickers=["FAKE"])
    res, _ = await ValuationService().run(req, data_service=ds, risk_free_rate=0.04)
    row = res.per_ticker[0]
    assert row.fcff is not None
    assert row.fcfe is not None
    assert row.fcff_value_per_share is not None
    assert row.fcfe_value_per_share is not None
    assert row.cost_of_equity is not None
    assert row.wacc is not None
    assert row.ddm_gordon is not None
    assert row.ddm_two_stage is not None


async def test_missing_tax_inputs_skips_ebit_based_valuation() -> None:
    ds = _minimal_fundamentals()
    inc, bal, cf, ov, prov = ds.get_fundamentals_bundle_for_valuation.return_value
    inc_missing_tax = {
        "annualReports": [{k: v for k, v in row.items() if k not in {"incomeTaxExpense"}} for row in inc["annualReports"]]
    }
    ds.get_fundamentals_bundle_for_valuation.return_value = (inc_missing_tax, bal, cf, ov, prov)

    res, _ = await ValuationService().run(
        ValuationRequest(tickers=["FAKE"]),
        data_service=ds,
        risk_free_rate=0.04,
    )

    row = res.per_ticker[0]
    drivers = res.export_drivers[0]
    assert drivers.tax_rate is None
    assert row.fcff is None
    assert row.fcfe is None
    assert row.wacc is None
    assert any("tax rate unavailable" in w.lower() for w in row.warnings)


async def test_missing_beta_and_failed_regression_nulls_cost_of_equity() -> None:
    ds = _minimal_fundamentals()
    inc, bal, cf, ov, prov = ds.get_fundamentals_bundle_for_valuation.return_value
    ov_no_beta = {k: v for k, v in ov.items() if k != "Beta"}
    ds.get_fundamentals_bundle_for_valuation.return_value = (inc, bal, cf, ov_no_beta, prov)

    async def _hist_side_effect(ticker: str, **kwargs: object) -> HistoricalResult:
        if ticker == "SPY":
            return _fake_monthly_hist(ticker)
        raise RuntimeError("history unavailable")

    ds.get_historical = AsyncMock(side_effect=_hist_side_effect)

    res, _ = await ValuationService().run(
        ValuationRequest(tickers=["FAKE"]),
        data_service=ds,
        risk_free_rate=0.04,
    )

    row = res.per_ticker[0]
    drivers = res.export_drivers[0]
    assert drivers.beta is None
    assert row.cost_of_equity is None
    assert row.wacc is None
    assert row.ddm_gordon is None
    assert any("beta unavailable" in w.lower() for w in row.warnings)


async def test_missing_annual_reports_does_not_invent_cost_of_equity() -> None:
    ds = AsyncMock()
    ds.get_fundamentals_bundle_for_valuation.return_value = (
        {"annualReports": []},
        {"annualReports": []},
        {"annualReports": []},
        {"Symbol": "MISS"},
        "yahoo",
    )
    ds.get_historical = AsyncMock(side_effect=lambda ticker, **kwargs: _fake_monthly_hist(ticker))

    res, _ = await ValuationService().run(
        ValuationRequest(tickers=["MISS"]),
        data_service=ds,
        risk_free_rate=0.04,
    )

    row = res.per_ticker[0]
    assert row.cost_of_equity is None
    assert row.fcff is None
    assert row.ddm_gordon is None
    assert any("missing annual reports" in w.lower() for w in row.warnings)


async def test_explicit_overrides_still_take_precedence() -> None:
    ds = _minimal_fundamentals()
    inc, bal, cf, ov, prov = ds.get_fundamentals_bundle_for_valuation.return_value
    ov_no_beta = {k: v for k, v in ov.items() if k != "Beta"}
    ds.get_fundamentals_bundle_for_valuation.return_value = (inc, bal, cf, ov_no_beta, prov)

    async def _hist_side_effect(ticker: str, **kwargs: object) -> HistoricalResult:
        if ticker == "SPY":
            return _fake_monthly_hist(ticker)
        raise RuntimeError("history unavailable")

    ds.get_historical = AsyncMock(side_effect=_hist_side_effect)

    req = ValuationRequest(
        tickers=["FAKE"],
        cost_of_equity_override=0.11,
        wacc=0.09,
        ddm_gordon_g=0.04,
        ddm_two_stage={"g1": 0.05, "g2": 0.03, "n_periods": 5},
    )
    res, _ = await ValuationService().run(req, data_service=ds, risk_free_rate=0.04)

    row = res.per_ticker[0]
    assert row.cost_of_equity == pytest.approx(0.11)
    assert row.wacc == pytest.approx(0.09)
    assert row.ddm_gordon is not None
    assert row.ddm_two_stage is not None


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


async def test_auto_growth_bounded_below_discount_rates() -> None:
    ds = _minimal_fundamentals()
    inc, bal, cf, ov, prov = ds.get_fundamentals_bundle_for_valuation.return_value
    ov_high_sgr = dict(ov)
    ov_high_sgr["returnOnEquity"] = "0.352"
    ov_high_sgr["payoutRatio"] = "0.603"
    ds.get_fundamentals_bundle_for_valuation.return_value = (inc, bal, cf, ov_high_sgr, prov)

    res, _ = await ValuationService().run(
        ValuationRequest(tickers=["FAKE"]),
        data_service=ds,
        risk_free_rate=0.04,
    )

    row = res.per_ticker[0]
    assert row.cost_of_equity is not None
    assert row.wacc is not None
    assert row.fcff_value_per_share is not None
    assert row.fcfe_value_per_share is not None
    assert row.ddm_gordon is not None
    assert row.ddm_two_stage is not None
    assert any("auto-adjusted" in w.lower() for w in row.warnings)
