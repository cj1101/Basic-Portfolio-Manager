"""Arithmetic and geometric *mean* simple monthly returns (not annualized)."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from .errors import InsufficientHistoryError, InvalidReturnWindowError


def simple_monthly_returns_from_close_series(closes: NDArray[np.float64]) -> NDArray[np.float64]:
    """``R_t = P_t / P_{t-1} - 1`` for ascending month-end `closes` (n >= 2)."""
    c = np.asarray(closes, dtype=np.float64).reshape(-1)
    if c.shape[0] < 2:
        raise InsufficientHistoryError(
            "need at least 2 month-end closes for monthly returns",
            {"n": int(c.shape[0])},
        )
    if not np.all(c > 0) or not np.all(np.isfinite(c)):
        raise InvalidReturnWindowError("month-end closes must be finite and strictly positive")
    return c[1:] / c[:-1] - 1.0


def mean_monthly_arithmetic_geometric(
    monthly_simple_returns: NDArray[np.float64],
) -> tuple[float, float]:
    r = np.asarray(monthly_simple_returns, dtype=np.float64).reshape(-1)
    if r.size < 1:
        raise InsufficientHistoryError("need at least one monthly return", {"n": int(r.size)})
    if not np.all(np.isfinite(r)):
        raise InvalidReturnWindowError("monthly returns must be finite")
    ar = float(r.mean())
    g = float(np.prod(1.0 + r) ** (1.0 / r.size) - 1.0)
    if not (math.isfinite(ar) and math.isfinite(g)):
        raise InvalidReturnWindowError("non-finite mean monthly return")
    return ar, g


__all__ = [
    "mean_monthly_arithmetic_geometric",
    "simple_monthly_returns_from_close_series",
]
