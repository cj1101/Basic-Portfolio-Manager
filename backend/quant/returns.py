"""Return-series helpers.

Annualization factors follow ``.cursor/rules/quant.mdc`` §1: daily ×252,
weekly ×52, monthly ×12; std devs use ``√factor``. The frequency is always
passed explicitly — it is never defaulted silently inside a math function.

These helpers are pure: they take numpy arrays of per-period returns and
return numpy arrays of annualized scalars. Raw-price → return conversion
belongs to the data layer (Agent 1A) and is *not* in scope here.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .errors import InsufficientHistoryError, InvalidReturnWindowError
from .types import ReturnFrequency

ANNUALIZATION_FACTORS: dict[ReturnFrequency, int] = {
    ReturnFrequency.DAILY: 252,
    ReturnFrequency.WEEKLY: 52,
    ReturnFrequency.MONTHLY: 12,
}


def annualization_factor(frequency: ReturnFrequency) -> int:
    if frequency not in ANNUALIZATION_FACTORS:
        raise InvalidReturnWindowError(
            f"Unsupported return frequency: {frequency!r}",
            {"frequency": str(frequency)},
        )
    return ANNUALIZATION_FACTORS[frequency]


def annualize_mean(mean_per_period: float, frequency: ReturnFrequency) -> float:
    return float(mean_per_period) * annualization_factor(frequency)


def annualize_std(std_per_period: float, frequency: ReturnFrequency) -> float:
    return float(std_per_period) * float(np.sqrt(annualization_factor(frequency)))


def annualize_variance(variance_per_period: float, frequency: ReturnFrequency) -> float:
    return float(variance_per_period) * annualization_factor(frequency)


def _require_2d_returns(returns: NDArray[np.float64]) -> NDArray[np.float64]:
    a = np.asarray(returns, dtype=np.float64)
    if a.ndim != 2:
        raise InvalidReturnWindowError(
            "returns must be a 2D array of shape (T, n)",
            {"shape": list(a.shape)},
        )
    if a.shape[0] < 2:
        raise InsufficientHistoryError(
            "need at least 2 observations to compute statistics",
            {"nObservations": int(a.shape[0])},
        )
    if not np.all(np.isfinite(a)):
        raise InvalidReturnWindowError(
            "returns contain NaN or Inf",
            {"nonFiniteCount": int(np.sum(~np.isfinite(a)))},
        )
    return a


def expected_returns(
    returns: NDArray[np.float64],
    frequency: ReturnFrequency,
) -> NDArray[np.float64]:
    """Annualized mean per column. ``returns`` has shape ``(T, n)``."""
    a = _require_2d_returns(returns)
    return a.mean(axis=0) * annualization_factor(frequency)


def std_devs(
    returns: NDArray[np.float64],
    frequency: ReturnFrequency,
    ddof: int = 1,
) -> NDArray[np.float64]:
    """Annualized std dev per column with Bessel-corrected sample variance by default."""
    a = _require_2d_returns(returns)
    return a.std(axis=0, ddof=ddof) * float(np.sqrt(annualization_factor(frequency)))


def sample_covariance(
    returns: NDArray[np.float64],
    frequency: ReturnFrequency,
    ddof: int = 1,
) -> NDArray[np.float64]:
    """Annualized sample covariance of the (T, n) return matrix."""
    a = _require_2d_returns(returns)
    cov = np.cov(a, rowvar=False, ddof=ddof)
    cov = np.atleast_2d(cov)
    cov = 0.5 * (cov + cov.T)
    return cov * annualization_factor(frequency)


__all__ = [
    "ANNUALIZATION_FACTORS",
    "annualization_factor",
    "annualize_mean",
    "annualize_std",
    "annualize_variance",
    "expected_returns",
    "sample_covariance",
    "std_devs",
]
