"""Treynor ratio: ``T = (E(r_p) − rᶠ) / β_p`` (``β_p = ∑ w_i β_i`` in the same units)."""

from __future__ import annotations

import math


def treynor_ratio(
    expected_portfolio_return: float,
    risk_free_rate: float,
    portfolio_beta: float,
) -> float:
    d = float(portfolio_beta)
    if not math.isfinite(d) or abs(d) < 1e-14:
        raise ValueError("portfolio_beta must be finite and not numerically zero")
    return (float(expected_portfolio_return) - float(risk_free_rate)) / d


__all__ = ["treynor_ratio"]
