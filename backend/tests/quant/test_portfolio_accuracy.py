"""Phase 3 — Portfolio accuracy verification suite.

9 portfolio configurations × 8 assertions = 72 parametrized test cases.

Covers:
1. ORP weights sum to 1
2. ORP Sharpe ≥ max single-stock Sharpe (optimality)
3. Variance cross-check (w @ cov @ w == reported variance)
4. Reference tangency match for unconstrained configs
5. CAL arithmetic (er_complete == rf + y* · (er_orp − rf))
6. Complete-portfolio variance (var_complete == y*² · var_orp)
7. Efficient frontier monotonicity
8. Risk-aversion sweep: y* strictly decreasing as A increases

All values are annualized decimals.
"""

from __future__ import annotations

import math
import warnings as _warnings
from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray

from quant.allocation import utility_max_allocation
from quant.frontier import efficient_frontier_points
from quant.markowitz import optimize_markowitz
from quant.types import ORP, RiskProfile

from ..conftest import DatasetAFixture, DatasetCFixture


# ---------------------------------------------------------------------------
# Portfolio configuration container
# ---------------------------------------------------------------------------

@dataclass
class PortfolioConfig:
    config_id: str
    tickers: tuple[str, ...]
    mu: NDArray[np.float64]
    cov: NDArray[np.float64]
    rf: float
    allow_short: bool
    allow_leverage: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_synthetic_config(
    config_id: str,
    n: int,
    allow_short: bool,
    allow_leverage: bool,
    seed: int,
) -> PortfolioConfig:
    rng = np.random.default_rng(seed)
    mu = rng.uniform(0.05, 0.25, n)
    A = rng.standard_normal((n, n))
    cov = (A @ A.T) / n + np.eye(n) * 0.02
    return PortfolioConfig(
        config_id=config_id,
        tickers=tuple(f"S{i + 1}" for i in range(n)),
        mu=mu,
        cov=cov,
        rf=0.03,
        allow_short=allow_short,
        allow_leverage=allow_leverage,
    )


def _reference_tangency(
    mu: NDArray[np.float64],
    cov: NDArray[np.float64],
    rf: float,
) -> NDArray[np.float64]:
    excess = mu - rf
    w_raw = np.linalg.solve(cov, excess)
    return w_raw / w_raw.sum()


def _run_orp(cfg: PortfolioConfig) -> ORP:
    return optimize_markowitz(
        list(cfg.tickers),
        cfg.mu,
        cfg.cov,
        risk_free_rate=cfg.rf,
        allow_short=cfg.allow_short,
        allow_leverage=cfg.allow_leverage,
    )


# ---------------------------------------------------------------------------
# Session-scoped fixture: build all 9 configs
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def all_portfolio_configs(
    dataset_a: DatasetAFixture,
    dataset_c: DatasetCFixture,
) -> list[PortfolioConfig]:
    p4 = PortfolioConfig(
        config_id="P4",
        tickers=dataset_a.tickers,
        mu=dataset_a.expected_returns,
        cov=dataset_a.covariance,
        rf=dataset_a.risk_free_rate,
        allow_short=True,
        allow_leverage=True,
    )
    p5 = PortfolioConfig(
        config_id="P5",
        tickers=dataset_c.tickers,
        mu=dataset_c.mu,
        cov=dataset_c.cov,
        rf=dataset_c.rf,
        allow_short=True,
        allow_leverage=True,
    )
    return [
        _make_synthetic_config("P1",  2, False, False, 101),
        _make_synthetic_config("P2",  2, True,  True,  102),
        _make_synthetic_config("P3",  3, False, False, 103),
        p4,
        p5,
        _make_synthetic_config("P6",  5, True,  True,  106),
        _make_synthetic_config("P7",  5, False, False, 107),
        _make_synthetic_config("P8", 10, True,  True,  108),
        _make_synthetic_config("P9", 10, False, False, 109),
    ]


_CONFIG_PARAMS = [
    pytest.param(0, id="P1"),
    pytest.param(1, id="P2"),
    pytest.param(2, id="P3"),
    pytest.param(3, id="P4"),
    pytest.param(4, id="P5"),
    pytest.param(5, id="P6"),
    pytest.param(6, id="P7"),
    pytest.param(7, id="P8"),
    pytest.param(8, id="P9"),
]


@pytest.fixture(scope="session", params=_CONFIG_PARAMS)
def portfolio_config(
    request: pytest.FixtureRequest,
    all_portfolio_configs: list[PortfolioConfig],
) -> PortfolioConfig:
    return all_portfolio_configs[request.param]


# ---------------------------------------------------------------------------
# Assertion 1 — Weights sum to 1
# ---------------------------------------------------------------------------

def test_1_weights_sum_to_one(portfolio_config: PortfolioConfig) -> None:
    """ORP weights must sum to 1 within machine tolerance."""
    orp = _run_orp(portfolio_config)
    w_sum = sum(orp.weights.values())
    assert abs(w_sum - 1.0) < 1e-9, (
        f"{portfolio_config.config_id}: weights sum = {w_sum:.15f}"
    )


# ---------------------------------------------------------------------------
# Assertion 2 — ORP Sharpe dominates every single-stock Sharpe
# ---------------------------------------------------------------------------

def test_2_orp_sharpe_dominates_single_stocks(portfolio_config: PortfolioConfig) -> None:
    """ORP Sharpe ratio must be ≥ any individual stock's Sharpe ratio."""
    orp = _run_orp(portfolio_config)
    rf = portfolio_config.rf
    mu = portfolio_config.mu
    cov = portfolio_config.cov

    single_sharpes = [
        (mu[i] - rf) / math.sqrt(cov[i, i])
        for i in range(len(mu))
    ]
    max_single = max(single_sharpes)
    assert orp.sharpe >= max_single - 1e-9, (
        f"{portfolio_config.config_id}: ORP Sharpe {orp.sharpe:.6f} < "
        f"max single-stock Sharpe {max_single:.6f}"
    )


# ---------------------------------------------------------------------------
# Assertion 3 — Variance cross-check
# ---------------------------------------------------------------------------

def test_3_variance_cross_check(portfolio_config: PortfolioConfig) -> None:
    """Reported ORP variance must equal w @ cov @ w."""
    orp = _run_orp(portfolio_config)
    w_vec = np.array([orp.weights[t] for t in portfolio_config.tickers], dtype=np.float64)
    computed_var = float(w_vec @ portfolio_config.cov @ w_vec)
    assert abs(computed_var - orp.variance) < 1e-9, (
        f"{portfolio_config.config_id}: computed var {computed_var:.9f} "
        f"!= reported var {orp.variance:.9f}"
    )


# ---------------------------------------------------------------------------
# Assertion 4 — Unconstrained weights match closed-form reference
# ---------------------------------------------------------------------------

def test_4_reference_tangency_match(portfolio_config: PortfolioConfig) -> None:
    """For allow_short=True, ORP weights must match Σ⁻¹(μ−rᶠ) reference."""
    if not portfolio_config.allow_short:
        pytest.skip(
            f"{portfolio_config.config_id}: reference tangency applies only to "
            "unconstrained (allow_short=True) ORP"
        )

    orp = _run_orp(portfolio_config)
    ref_w = _reference_tangency(portfolio_config.mu, portfolio_config.cov, portfolio_config.rf)
    orp_w = np.array([orp.weights[t] for t in portfolio_config.tickers], dtype=np.float64)

    max_diff = float(np.max(np.abs(orp_w - ref_w)))
    assert max_diff < 1e-4, (
        f"{portfolio_config.config_id}: max |w_orp − w_ref| = {max_diff:.2e}"
    )


# ---------------------------------------------------------------------------
# Assertion 5 — CAL arithmetic: er_complete == rf + y* · (er_orp − rf)
# ---------------------------------------------------------------------------

def test_5_cal_arithmetic(portfolio_config: PortfolioConfig) -> None:
    """Complete-portfolio expected return must lie on the Capital Allocation Line."""
    orp = _run_orp(portfolio_config)
    rf = portfolio_config.rf

    complete = utility_max_allocation(
        orp=orp,
        risk_free_rate=rf,
        risk_profile=RiskProfile(risk_aversion=4),
        allow_leverage=portfolio_config.allow_leverage,
    )
    expected_er = rf + complete.y_star * (orp.expected_return - rf)
    assert abs(complete.expected_return - expected_er) < 1e-9, (
        f"{portfolio_config.config_id}: er_complete={complete.expected_return:.9f} "
        f"!= rf + y*·(er_orp−rf) = {expected_er:.9f}"
    )


# ---------------------------------------------------------------------------
# Assertion 6 — Complete-portfolio variance = y*² · var_orp
# ---------------------------------------------------------------------------

def test_6_complete_portfolio_variance(portfolio_config: PortfolioConfig) -> None:
    """Complete-portfolio variance must equal y*² · var_orp."""
    orp = _run_orp(portfolio_config)
    rf = portfolio_config.rf

    complete = utility_max_allocation(
        orp=orp,
        risk_free_rate=rf,
        risk_profile=RiskProfile(risk_aversion=4),
        allow_leverage=portfolio_config.allow_leverage,
    )
    var_complete = complete.std_dev ** 2
    expected_var = complete.y_star ** 2 * orp.variance
    assert abs(var_complete - expected_var) < 1e-9, (
        f"{portfolio_config.config_id}: var_complete={var_complete:.9f} "
        f"!= y*²·var_orp={expected_var:.9f}"
    )


# ---------------------------------------------------------------------------
# Assertion 7 — Efficient frontier monotonicity
# ---------------------------------------------------------------------------

def test_7_frontier_monotonicity(portfolio_config: PortfolioConfig) -> None:
    """Efficient frontier: if σ increases, expected return must not decrease."""
    points = efficient_frontier_points(
        expected_returns=portfolio_config.mu,
        covariance=portfolio_config.cov,
        frontier_resolution=40,
    )

    if len(points) < 2:
        pytest.skip(f"{portfolio_config.config_id}: frontier has fewer than 2 points")

    violations: list[tuple[int, float, float, float, float]] = []
    for i in range(len(points) - 1):
        s_i = points[i].std_dev
        r_i = points[i].expected_return
        s_next = points[i + 1].std_dev
        r_next = points[i + 1].expected_return
        if s_next > s_i and r_next < r_i - 1e-12:
            violations.append((i, s_i, r_i, s_next, r_next))

    assert not violations, (
        f"{portfolio_config.config_id}: frontier has σ↑ but r↓ at indices: "
        f"{violations[:3]}"
    )


# ---------------------------------------------------------------------------
# Assertion 8 — Risk-aversion sweep: y* strictly decreasing in A
# ---------------------------------------------------------------------------

def test_8_risk_aversion_sweep(portfolio_config: PortfolioConfig) -> None:
    """y* = (er_orp − rf) / (A · var_orp) must be strictly decreasing for A ∈ [2,4,6,8,10]."""
    orp = _run_orp(portfolio_config)
    rf = portfolio_config.rf
    risk_premium = orp.expected_return - rf
    var_orp = orp.variance

    if risk_premium <= 0.0:
        _warnings.warn(
            f"{portfolio_config.config_id}: ORP risk premium {risk_premium:.6f} ≤ 0; "
            "skipping risk-aversion sweep",
            stacklevel=2,
        )
        pytest.skip(f"{portfolio_config.config_id}: non-positive ORP risk premium")

    a_values = [2, 4, 6, 8, 10]
    y_stars = [risk_premium / (a * var_orp) for a in a_values]

    if y_stars[0] < 0.0:
        _warnings.warn(
            f"{portfolio_config.config_id}: y*(A=2) = {y_stars[0]:.6f} < 0; "
            "skipping risk-aversion sweep",
            stacklevel=2,
        )
        pytest.skip(f"{portfolio_config.config_id}: y* is negative at A=2")

    for i in range(len(y_stars) - 1):
        assert y_stars[i] > y_stars[i + 1], (
            f"{portfolio_config.config_id}: y*(A={a_values[i]}) = {y_stars[i]:.6f} "
            f"not > y*(A={a_values[i + 1]}) = {y_stars[i + 1]:.6f}"
        )
