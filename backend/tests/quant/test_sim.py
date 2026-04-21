"""Tests for ``quant.sim`` (Single-Index Model regression)."""

from __future__ import annotations

import numpy as np
import pytest

from quant.errors import InsufficientHistoryError, InvalidReturnWindowError
from quant.sim import single_index_metrics


def test_recovers_known_beta_alpha() -> None:
    """Synthesise r_i = α + β·r_M + e and check OLS recovers α, β."""
    rng = np.random.default_rng(2024)
    n = 2000
    r_m = rng.normal(loc=0.0005, scale=0.01, size=n)
    true_alpha = 0.0002
    true_beta = 1.25
    e = rng.normal(loc=0.0, scale=0.005, size=n)
    r_i = true_alpha + true_beta * r_m + e

    fit = single_index_metrics(r_i, r_m, risk_free_per_period=0.0)
    # n = 2000 synthetic samples; OLS beta standard error is ~0.005 so a
    # 1e-2 tolerance is a reasonable 2-sigma bound.
    assert fit.beta == pytest.approx(true_beta, abs=1e-2)
    assert fit.alpha_per_period == pytest.approx(true_alpha, abs=5e-4)
    assert fit.firm_specific_var_per_period == pytest.approx(0.005**2, rel=1e-1)
    assert fit.n_observations == n


def test_shape_mismatch_raises() -> None:
    with pytest.raises(InvalidReturnWindowError):
        single_index_metrics(np.zeros(10), np.zeros(11))


def test_insufficient_history_raises() -> None:
    with pytest.raises(InsufficientHistoryError):
        single_index_metrics(np.zeros(1), np.zeros(1))


def test_zero_market_variance_raises() -> None:
    with pytest.raises(InvalidReturnWindowError):
        single_index_metrics(np.array([0.01, 0.02, 0.03]), np.array([0.01, 0.01, 0.01]))


def test_non_finite_raises() -> None:
    with pytest.raises(InvalidReturnWindowError):
        single_index_metrics(
            np.array([0.0, np.nan, 0.0]),
            np.array([0.0, 0.0, 0.0]),
        )


def test_firm_variance_on_collinear_series() -> None:
    """Collinear ``r_i = β·r_M`` → σ²(e) is zero (or tiny float drift).

    Whether the computed value comes out as exactly 0, a tiny positive
    number, or a tiny negative number depends on floating-point rounding in
    numpy's ``cov`` routine. The function must always produce a non-negative
    output; if drift pushed it slightly negative, the clamp-and-warn path
    engages.
    """
    n = 500
    rng = np.random.default_rng(1)
    r_m = rng.normal(scale=0.01, size=n)
    beta = 1.1
    r_i = beta * r_m
    warnings: list[str] = []
    fit = single_index_metrics(r_i, r_m, warnings=warnings)
    assert fit.firm_specific_var_per_period >= 0.0
    assert fit.firm_specific_var_per_period < 1e-10
    assert fit.beta == pytest.approx(beta, abs=1e-12)
    assert fit.alpha_per_period == pytest.approx(0.0, abs=1e-12)
