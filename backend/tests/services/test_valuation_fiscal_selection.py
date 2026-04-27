"""Synchronous tests for valuation fiscal-period selection (no async fixtures)."""

from __future__ import annotations

from datetime import date as Date

from app.services.valuation_service import select_annual_reports_as_of


def test_select_statements_latest_fiscal_on_or_before_window() -> None:
    tw: list[str] = []
    ann_i = [
        {"fiscalDateEnding": "2024-09-30", "ebit": "100", "totalRevenue": "500"},
        {"fiscalDateEnding": "2023-09-30", "ebit": "90", "totalRevenue": "400"},
    ]
    ann_b = [
        {"fiscalDateEnding": "2024-09-30", "totalDebt": "80"},
        {"fiscalDateEnding": "2023-09-30", "totalDebt": "78"},
    ]
    ann_c = [
        {"fiscalDateEnding": "2024-09-30", "capitalExpenditures": "-10"},
        {"fiscalDateEnding": "2023-09-30", "capitalExpenditures": "-9"},
    ]
    i0, c0, b0, b1 = select_annual_reports_as_of(
        ann_i, ann_b, ann_c, Date(2024, 6, 1), tw
    )
    assert i0["ebit"] == "90"
    assert b0["totalDebt"] == "78"
    assert c0["capitalExpenditures"] == "-9"
    assert b1["totalDebt"] == "78"
