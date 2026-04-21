"""End-to-end Dataset A pipeline: every number within 1e-6 in one test."""

from __future__ import annotations

import pytest

from quant.allocation import utility_max_allocation
from quant.frontier import cal_points, efficient_frontier_points
from quant.linalg import build_covariance
from quant.markowitz import optimize_markowitz
from quant.minvar import minimum_variance_portfolio
from quant.types import RiskProfile

from ..conftest import DatasetAFixture, TOLERANCE_SCALAR, TOLERANCE_WEIGHT_SUM


def test_dataset_a_round_trip(dataset_a: DatasetAFixture) -> None:
    warnings: list[str] = []

    cov = build_covariance(dataset_a.std_devs, dataset_a.correlation)
    for i in range(3):
        for j in range(3):
            assert cov[i, j] == pytest.approx(dataset_a.covariance[i, j], abs=1e-12)

    orp = optimize_markowitz(
        list(dataset_a.tickers),
        dataset_a.expected_returns,
        cov,
        risk_free_rate=dataset_a.risk_free_rate,
        allow_short=True,
        allow_leverage=True,
        warnings=warnings,
    )
    for t, w in dataset_a.orp_weights.items():
        assert orp.weights[t] == pytest.approx(w, abs=TOLERANCE_SCALAR)
    assert orp.expected_return == pytest.approx(
        dataset_a.orp_expected_return, abs=TOLERANCE_SCALAR
    )
    assert orp.std_dev == pytest.approx(dataset_a.orp_std_dev, abs=TOLERANCE_SCALAR)
    assert orp.variance == pytest.approx(dataset_a.orp_variance, abs=TOLERANCE_SCALAR)
    assert orp.sharpe == pytest.approx(dataset_a.orp_sharpe, abs=TOLERANCE_SCALAR)
    assert sum(orp.weights.values()) == pytest.approx(1.0, abs=TOLERANCE_WEIGHT_SUM)

    mvp = minimum_variance_portfolio(
        list(dataset_a.tickers),
        dataset_a.expected_returns,
        cov,
        risk_free_rate=dataset_a.risk_free_rate,
        allow_short=True,
        warnings=warnings,
    )
    for t, w in dataset_a.mvp_weights.items():
        assert mvp.weights[t] == pytest.approx(w, abs=TOLERANCE_SCALAR)
    assert mvp.expected_return == pytest.approx(
        dataset_a.mvp_expected_return, abs=TOLERANCE_SCALAR
    )
    assert mvp.std_dev == pytest.approx(dataset_a.mvp_std_dev, abs=TOLERANCE_SCALAR)

    complete_lev = utility_max_allocation(
        orp=orp,
        risk_free_rate=dataset_a.risk_free_rate,
        risk_profile=RiskProfile(risk_aversion=4),
        allow_leverage=True,
        warnings=warnings,
    )
    assert complete_lev.y_star == pytest.approx(1.5625, abs=TOLERANCE_SCALAR)
    assert complete_lev.leverage_used is True
    assert complete_lev.expected_return == pytest.approx(0.170625, abs=TOLERANCE_SCALAR)
    assert complete_lev.std_dev == pytest.approx(0.180711, abs=TOLERANCE_SCALAR)

    complete_nolev = utility_max_allocation(
        orp=orp,
        risk_free_rate=dataset_a.risk_free_rate,
        risk_profile=RiskProfile(risk_aversion=8),
        allow_leverage=True,
        warnings=warnings,
    )
    assert complete_nolev.y_star == pytest.approx(0.78125, abs=TOLERANCE_SCALAR)
    assert complete_nolev.leverage_used is False
    assert complete_nolev.expected_return == pytest.approx(0.105313, abs=TOLERANCE_SCALAR)
    assert complete_nolev.std_dev == pytest.approx(0.090356, abs=TOLERANCE_SCALAR)

    frontier = efficient_frontier_points(
        dataset_a.expected_returns, cov, frontier_resolution=40, warnings=warnings
    )
    assert len(frontier) == 40
    cal = cal_points(
        orp,
        risk_free_rate=dataset_a.risk_free_rate,
        y_star=complete_lev.y_star,
        resolution=21,
    )
    assert cal[0].std_dev == pytest.approx(0.0)
    assert cal[0].expected_return == pytest.approx(dataset_a.risk_free_rate)
    assert cal[-1].y >= 1.5625

    # All good inputs → no warnings from any stage.
    assert warnings == []
