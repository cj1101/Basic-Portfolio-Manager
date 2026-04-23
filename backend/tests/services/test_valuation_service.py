"""ValuationService with mocked fundamentals."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.schemas import ValuationRequest
from app.services.valuation_service import ValuationService

pytestmark = pytest.mark.asyncio


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
