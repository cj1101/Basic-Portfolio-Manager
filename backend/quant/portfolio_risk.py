"""Portfolio ORP/complete performance: SIM variance split (β_p²σ²_M + ∑ w_i²σ²(e_i))."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

SIM_MISMATCH_WARN_TOL = 1e-5


def portfolio_beta(
    weights: NDArray[np.float64],
    betas: NDArray[np.float64],
) -> float:
    w = np.asarray(weights, dtype=np.float64).reshape(-1)
    b = np.asarray(betas, dtype=np.float64).reshape(-1)
    if w.shape != b.shape or w.size == 0:
        raise ValueError("weights and betas must have the same non-empty shape")
    return float(np.dot(w, b))


def sim_portfolio_variance_decomposition(
    weights: NDArray[np.float64],
    betas: NDArray[np.float64],
    market_variance: float,
    firm_specific_vars: NDArray[np.float64],
) -> tuple[float, float, float]:
    """Return ``(systematic, unsystematic, sim_sum)`` where ``sim_sum = sys + unsy``."""
    w = np.asarray(weights, dtype=np.float64).reshape(-1)
    b = np.asarray(betas, dtype=np.float64).reshape(-1)
    fe = np.asarray(firm_specific_vars, dtype=np.float64).reshape(-1)
    if not (w.shape == b.shape == fe.shape):
        raise ValueError("weights, betas, and firm_specific_vars must align")
    vm = float(market_variance)
    if vm < 0:
        raise ValueError("market_variance must be non-negative")
    p_beta = float(np.dot(w, b))
    systematic = p_beta**2 * vm
    unsystematic = float(np.sum((w**2) * fe))
    sim_sum = systematic + unsystematic
    return systematic, unsystematic, sim_sum


def total_variance_from_covariance(
    covariance: NDArray[np.float64],
    weights: NDArray[np.float64],
) -> float:
    w = np.asarray(weights, dtype=np.float64).reshape(-1, 1)
    cov = np.asarray(covariance, dtype=np.float64)
    if cov.shape[0] != cov.shape[1] or w.shape[0] != cov.shape[0]:
        raise ValueError("covariance and weights are incompatible")
    v = w.T @ cov @ w
    return float(v[0, 0])


__all__ = [
    "SIM_MISMATCH_WARN_TOL",
    "portfolio_beta",
    "sim_portfolio_variance_decomposition",
    "total_variance_from_covariance",
]
