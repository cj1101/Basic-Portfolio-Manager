"""Tests for FCFF applicability heuristics."""

from __future__ import annotations

from quant.valuation_eligibility import skip_ebit_based_fcff


def test_known_bank_ticker_skips_without_overview() -> None:
    ov: dict = {}
    inc = {"totalRevenue": "1000"}
    bal = {"totalCurrentLiabilities": "200"}
    assert skip_ebit_based_fcff("JPM", ov, inc, bal) is True


def test_sector_financial_skips() -> None:
    ov = {"Sector": "FINANCIAL SERVICES", "Industry": "Software"}
    inc = {"totalRevenue": "1000"}
    bal = {"totalCurrentLiabilities": "200"}
    assert skip_ebit_based_fcff("XYZ", ov, inc, bal) is True


def test_high_current_liabilities_to_revenue_skips() -> None:
    ov = {"Sector": "Unknown", "Industry": "Unknown"}
    inc = {"totalRevenue": "100"}
    bal = {"totalCurrentLiabilities": "500"}
    assert skip_ebit_based_fcff("XYZ", ov, inc, bal) is True


def test_typical_industrial_passes() -> None:
    ov = {"Sector": "TECHNOLOGY", "Industry": "CONSUMER ELECTRONICS"}
    inc = {"totalRevenue": "400000000000"}
    bal = {"totalCurrentLiabilities": "130000000000"}
    assert skip_ebit_based_fcff("AAPL", ov, inc, bal) is False


def test_lowercase_overview_keys() -> None:
    ov = {"sector": "financial services", "industry": "banks - diversified"}
    inc = {"totalRevenue": "1000"}
    bal = {"totalCurrentLiabilities": "200"}
    assert skip_ebit_based_fcff("X", ov, inc, bal) is True
