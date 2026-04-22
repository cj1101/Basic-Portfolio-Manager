"""Dividend discount models: Gordon and two-stage (pure, per share)."""

from __future__ import annotations

import math


def ddm_gordon(
    d1: float,
    cost_of_equity: float,
    growth: float,
) -> float:
    if not all(math.isfinite(x) for x in (d1, cost_of_equity, growth)):
        raise ValueError("d1, k_e, and g must be finite")
    if cost_of_equity <= growth:
        raise ValueError("k_e must exceed g in Gordon DDM")
    return float(d1) / (cost_of_equity - growth)


def ddm_two_stage(
    d0: float,
    g1: float,
    g2: float,
    n_periods: int,
    cost_of_equity: float,
) -> float:
    """D0 is last paid dividend. Stage-1: grow at g1 for N years; then g2 to infinity."""
    if n_periods < 1 or not float(n_periods).is_integer():
        raise ValueError("n_periods must be a positive integer")
    n = int(n_periods)
    k = cost_of_equity
    if not all(math.isfinite(x) for x in (d0, g1, g2, k)):
        raise ValueError("inputs must be finite")
    if k <= g1 or k <= g2:
        raise ValueError("k_e must exceed both growth rates")
    d = float(d0)
    pv = 0.0
    for t in range(1, n + 1):
        d = d * (1.0 + g1)
        pv += d / (1.0 + k) ** t
    d_next = d * (1.0 + g2)
    terminal = d_next / (k - g2) / (1.0 + k) ** n
    return float(pv + terminal)


__all__ = [
    "ddm_gordon",
    "ddm_two_stage",
]
