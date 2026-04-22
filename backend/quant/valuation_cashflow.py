"""FCFF, FCFE, and single-stage per-share DCF from cash-flow inputs (pure)."""

from __future__ import annotations

import math


def fcff_nopat_depre_capex_deltanwc(
    ebit: float,
    tax_rate: float,
    depreciation: float,
    capex: float,
    delta_nwc: float,
) -> float:
    """``EBIT(1–Tc) + D&A – CapEx – ΔNWC``."""
    t = max(0.0, min(1.0, float(tax_rate)))
    return float(ebit) * (1.0 - t) + float(depreciation) - float(capex) - float(delta_nwc)


def fcfe_from_fcff(
    fcff: float,
    interest_expense: float,
    tax_rate: float,
    net_borrowing: float,
) -> float:
    """``FCFF – Interest(1–Tc) + Net borrowing`` (sign convention: borrowing positive)."""
    t = max(0.0, min(1.0, float(tax_rate)))
    return float(fcff) - float(interest_expense) * (1.0 - t) + float(net_borrowing)


def fcff_firm_value_perpetuity(
    fcff0: float,
    wacc: float,
    growth: float,
) -> float:
    if not math.isfinite(fcff0) or not math.isfinite(wacc) or not math.isfinite(growth):
        raise ValueError("fcff, wacc, and growth must be finite")
    if wacc <= growth:
        raise ValueError("wacc must exceed growth in Gordon perpetuity for FCFF")
    return float(fcff0) * (1.0 + float(growth)) / (wacc - growth)


def fcfe_equity_value_perpetuity(
    fcfe0: float,
    cost_of_equity: float,
    growth: float,
) -> float:
    if not math.isfinite(fcfe0) or not math.isfinite(cost_of_equity) or not math.isfinite(growth):
        raise ValueError("fcfe, k_e, and g must be finite")
    if cost_of_equity <= growth:
        raise ValueError("cost_of_equity must exceed growth in Gordon perpetuity for FCFE")
    return float(fcfe0) * (1.0 + float(growth)) / (cost_of_equity - growth)


def equity_value_from_enterprise_value(enterprise_value: float, net_debt: float) -> float:
    """Book bridge: equity value ≈ enterprise value minus net debt (debt minus cash).

    ``net_debt`` is interest-bearing debt less cash and equivalents on the same balance date.
    """
    if not math.isfinite(enterprise_value) or not math.isfinite(net_debt):
        raise ValueError("enterprise_value and net_debt must be finite")
    return float(enterprise_value) - float(net_debt)


def per_share(equity_value: float, shares_out: float) -> float | None:
    if not math.isfinite(equity_value) or not math.isfinite(shares_out) or shares_out <= 0:
        return None
    return float(equity_value) / float(shares_out)


__all__ = [
    "equity_value_from_enterprise_value",
    "fcfe_equity_value_perpetuity",
    "fcfe_from_fcff",
    "fcff_firm_value_perpetuity",
    "fcff_nopat_depre_capex_deltanwc",
    "per_share",
]
