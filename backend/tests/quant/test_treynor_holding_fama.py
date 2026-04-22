"""Treynor, holding-period, and Fama–French 3 (Dataset A style)."""

from __future__ import annotations

import numpy as np
import pytest

from quant.fama_french_3 import (
    capm_expected_return_annualized,
    fama_french_capm_regression_mkt,
    fama_french_three_regression,
    expected_return_from_monthly_sample_means,
)
from quant.holding_period_monthly import mean_monthly_arithmetic_geometric, simple_monthly_returns_from_close_series
from quant.portfolio_risk import sim_portfolio_variance_decomposition, total_variance_from_covariance
from quant.treynor import treynor_ratio


def test_treynor_ratio_dataset_a_orn() -> None:
    w = np.array([0.426667, 0.360000, 0.213333], dtype=np.float64)
    b = np.array([0.80, 1.10, 1.50], dtype=np.float64)
    e_orp = 0.123600
    rf = 0.04
    beta_p = float(np.dot(w, b))
    t = treynor_ratio(e_orp, rf, beta_p)
    assert t == pytest.approx(0.07907, rel=1e-4)


def test_sim_decomposition_sums() -> None:
    w = np.array([0.3, 0.7], dtype=np.float64)
    b = np.array([0.5, 1.2], dtype=np.float64)
    vm = 0.04
    f = np.array([0.01, 0.02], dtype=np.float64)
    sysv, unsyv, ssum = sim_portfolio_variance_decomposition(w, b, vm, f)
    assert ssum == pytest.approx(sysv + unsyv)
    cov = np.diag([0.1, 0.11])
    tv = total_variance_from_covariance(cov, w)
    assert tv > 0


def test_holding_arithmetic_geometric() -> None:
    closes = np.array([100.0, 101.0, 103.02], dtype=np.float64)  # +1%, +2%
    r = simple_monthly_returns_from_close_series(closes)
    ar, geo = mean_monthly_arithmetic_geometric(r)
    assert ar == pytest.approx(0.015, rel=1e-9)
    assert geo == pytest.approx((1.01 * 1.02) ** (1 / 2) - 1.0, rel=1e-9)


def test_fama_french3_recovers_betas() -> None:
    n = 24
    rng = np.random.default_rng(0)
    m = rng.normal(0, 0.01, n)
    s = rng.normal(0, 0.01, n)
    h = rng.normal(0, 0.01, n)
    y = 0.5 * m - 0.2 * s + 0.1 * h + rng.normal(0, 0.001, n)
    a, b1, b2, b3, n3 = fama_french_three_regression(y, m, s, h)
    assert b1 == pytest.approx(0.5, rel=0.1)
    assert n3 == n
    a2, bcap, n2 = fama_french_capm_regression_mkt(y, m)
    assert n2 == n
    m_rf = float(np.mean(np.zeros(n)))
    eff = expected_return_from_monthly_sample_means(0.0, float(np.mean(m)), float(np.mean(s)), float(np.mean(h)), b1, b2, b3)
    ec = capm_expected_return_annualized(0.0, float(np.mean(m)), bcap)
    assert np.isfinite(eff) and np.isfinite(ec)
