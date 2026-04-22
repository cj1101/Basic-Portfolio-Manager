"""FCFF / FCFE pure formulas (Damodaran-style single-year bridge)."""

from __future__ import annotations

import pytest

from quant.valuation_cashflow import (
    equity_value_from_enterprise_value,
    fcfe_equity_value_perpetuity,
    fcfe_from_fcff,
    fcff_firm_value_perpetuity,
    fcff_nopat_depre_capex_deltanwc,
    per_share,
)


def test_fcff_nopat_bridge() -> None:
    # EBIT 100, Tc 21%, D&A 10, CapEx 30, ΔNWC 5
    # NOPAT 79 + 10 - 30 - 5 = 54
    got = fcff_nopat_depre_capex_deltanwc(
        ebit=100.0,
        tax_rate=0.21,
        depreciation=10.0,
        capex=30.0,
        delta_nwc=5.0,
    )
    assert got == pytest.approx(54.0)


def test_fcfe_from_fcff() -> None:
    # FCFE = FCFF - Int(1-T) + net borrowing
    got = fcfe_from_fcff(
        fcff=54.0,
        interest_expense=10.0,
        tax_rate=0.21,
        net_borrowing=5.0,
    )
    assert got == pytest.approx(54.0 - 7.9 + 5.0)


def test_fcff_firm_value_perpetuity() -> None:
    # V0 = FCFF1 / (WACC - g), FCFF1 = FCFF0 * (1+g)
    got = fcff_firm_value_perpetuity(fcff0=100.0, wacc=0.10, growth=0.02)
    assert got == pytest.approx(100.0 * 1.02 / 0.08)


def test_fcfe_equity_value_perpetuity() -> None:
    got = fcfe_equity_value_perpetuity(fcfe0=50.0, cost_of_equity=0.11, growth=0.02)
    assert got == pytest.approx(50.0 * 1.02 / 0.09)


def test_equity_from_ev_and_per_share() -> None:
    ev = fcff_firm_value_perpetuity(100.0, 0.10, 0.02)
    eq = equity_value_from_enterprise_value(ev, net_debt=300.0)
    assert eq == pytest.approx(ev - 300.0)
    assert per_share(eq, 10.0) == pytest.approx(eq / 10.0)


def test_perpetuity_requires_wacc_above_growth() -> None:
    with pytest.raises(ValueError, match="wacc"):
        fcff_firm_value_perpetuity(100.0, wacc=0.02, growth=0.02)
