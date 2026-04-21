"""Sharpe ratio.

``SR = (E(r_p) − rᶠ) / σ_p``. Annualized inputs in, annualized scalar out.
"""

from __future__ import annotations

import math


def sharpe_ratio(
    expected_return: float,
    std_dev: float,
    risk_free_rate: float,
) -> float:
    e_r = float(expected_return)
    sd = float(std_dev)
    rf = float(risk_free_rate)
    if not (math.isfinite(e_r) and math.isfinite(sd) and math.isfinite(rf)):
        raise ValueError("sharpe_ratio received a non-finite input")
    if sd <= 0.0:
        raise ValueError(f"std_dev must be strictly positive; got {sd}")
    return (e_r - rf) / sd


__all__ = ["sharpe_ratio"]
