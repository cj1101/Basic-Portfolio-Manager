"""Fama–French 3 factor OLS and expected return from sample factor means (monthly)."""

from __future__ import annotations

import numpy as np
from numpy.linalg import lstsq
from numpy.typing import NDArray

from .errors import InsufficientHistoryError, InvalidReturnWindowError


def fama_french_three_regression(
    stock_excess: NDArray[np.float64],  # R - RF
    mkt_rf: NDArray[np.float64],
    smb: NDArray[np.float64],
    hml: NDArray[np.float64],
) -> tuple[float, float, float, float, int]:
    """``y = α + β1 MktRF + β2 SMB + β3 HML``; returns (alpha, b1, b2, b3, n). Per-period, not annualized alpha."""
    y = np.asarray(stock_excess, dtype=np.float64).reshape(-1)
    x1 = np.asarray(mkt_rf, dtype=np.float64).reshape(-1)
    x2 = np.asarray(smb, dtype=np.float64).reshape(-1)
    x3 = np.asarray(hml, dtype=np.float64).reshape(-1)
    n = y.shape[0]
    if not (n == x1.shape[0] == x2.shape[0] == x3.shape[0]):
        raise InvalidReturnWindowError("FF3: misaligned input lengths")
    if n < 4:
        raise InsufficientHistoryError(
            "need at least 4 months for 3-factor OLS", {"n": n, "required": 4}
        )
    if not (
        np.all(np.isfinite(y))
        and np.all(np.isfinite(x1))
        and np.all(np.isfinite(x2))
        and np.all(np.isfinite(x3))
    ):
        raise InvalidReturnWindowError("FF3: non-finite values")
    X = np.column_stack([np.ones(n), x1, x2, x3])
    coef, _, _, _ = lstsq(X, y, rcond=None)
    alpha = float(coef[0])
    b1, b2, b3 = float(coef[1]), float(coef[2]), float(coef[3])
    return alpha, b1, b2, b3, n


def fama_french_capm_regression_mkt(
    stock_excess: NDArray[np.float64],
    mkt_rf: NDArray[np.float64],
) -> tuple[float, float, int]:
    y = np.asarray(stock_excess, dtype=np.float64).reshape(-1)
    x1 = np.asarray(mkt_rf, dtype=np.float64).reshape(-1)
    n = y.shape[0]
    if n != x1.shape[0]:
        raise InvalidReturnWindowError("CAPM monthly: length mismatch")
    if n < 2:
        raise InsufficientHistoryError("need at least 2 months for CAPM OLS", {"n": n})
    X = np.column_stack([np.ones(n), x1])
    coef, _, _, _ = lstsq(X, y, rcond=None)
    return float(coef[0]), float(coef[1]), n


def expected_return_from_monthly_sample_means(
    mean_rf: float,
    mkt_mean: float,
    smb_mean: float,
    hml_mean: float,
    b_mkt: float,
    b_smb: float,
    b_hml: float,
) -> float:
    """`E(r) = RF̄ + ∑ β F̄` in monthly *mean* form, then ×12 to annualize."""
    e_m = float(mean_rf) + b_mkt * mkt_mean + b_smb * smb_mean + b_hml * hml_mean
    return e_m * 12.0


def capm_expected_return_annualized(
    mean_rf: float,
    mean_mkt_rf: float,
    beta: float,
) -> float:
    return (float(mean_rf) + float(beta) * float(mean_mkt_rf)) * 12.0


def annualize_alpha_monthly(alpha_m: float) -> float:
    return float(alpha_m) * 12.0


__all__ = [
    "annualize_alpha_monthly",
    "capm_expected_return_annualized",
    "expected_return_from_monthly_sample_means",
    "fama_french_capm_regression_mkt",
    "fama_french_three_regression",
]
