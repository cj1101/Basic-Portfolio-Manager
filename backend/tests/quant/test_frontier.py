"""Tests for ``quant.frontier``."""

from __future__ import annotations

import numpy as np
import pytest

from quant.errors import OptimizerInfeasibleError
from quant.frontier import cal_points, efficient_frontier_points
from quant.types import ORP

from ..conftest import DatasetAFixture, TOLERANCE_SCALAR


class TestEfficientFrontier:
    def test_resolution_respected(self, dataset_a: DatasetAFixture) -> None:
        points = efficient_frontier_points(
            dataset_a.expected_returns,
            dataset_a.covariance,
            frontier_resolution=40,
        )
        assert len(points) == 40

    def test_monotone_in_both_axes(self, dataset_a: DatasetAFixture) -> None:
        points = efficient_frontier_points(
            dataset_a.expected_returns,
            dataset_a.covariance,
            frontier_resolution=40,
        )
        for prev, nxt in zip(points, points[1:], strict=False):
            assert nxt.expected_return >= prev.expected_return - TOLERANCE_SCALAR
            assert nxt.std_dev >= prev.std_dev - TOLERANCE_SCALAR

    def test_passes_through_mvp_and_orp(self, dataset_a: DatasetAFixture) -> None:
        """Any (σ, μ) on the efficient branch must satisfy Merton's hyperbola;
        in particular, plugging E(r_MVP) and E(r_ORP) should recover σ_MVP and
        σ_ORP respectively."""
        a_const = float(np.ones(3) @ np.linalg.solve(dataset_a.covariance, np.ones(3)))
        b_const = float(
            np.ones(3) @ np.linalg.solve(dataset_a.covariance, dataset_a.expected_returns)
        )
        c_const = float(
            dataset_a.expected_returns
            @ np.linalg.solve(dataset_a.covariance, dataset_a.expected_returns)
        )
        d_const = a_const * c_const - b_const * b_const

        for mu_target, expected_sd in [
            (dataset_a.mvp_expected_return, dataset_a.mvp_std_dev),
            (dataset_a.orp_expected_return, dataset_a.orp_std_dev),
        ]:
            var = (a_const * mu_target * mu_target - 2 * b_const * mu_target + c_const) / d_const
            assert float(np.sqrt(var)) == pytest.approx(expected_sd, abs=TOLERANCE_SCALAR)

    def test_resolution_too_small_raises(self, dataset_a: DatasetAFixture) -> None:
        with pytest.raises(ValueError):
            efficient_frontier_points(
                dataset_a.expected_returns,
                dataset_a.covariance,
                frontier_resolution=4,
            )

    def test_degenerate_inputs_raise(self) -> None:
        mu = np.array([0.1, 0.1])
        cov = np.array([[0.04, 0.04], [0.04, 0.04]])
        with pytest.raises(Exception):  # non-PSD or infeasible  # noqa: B017
            efficient_frontier_points(mu, cov, frontier_resolution=20)


class TestCAL:
    def test_passes_through_rf_and_orp(self, dataset_a: DatasetAFixture) -> None:
        orp = ORP(
            weights=dict(dataset_a.orp_weights),
            expected_return=dataset_a.orp_expected_return,
            std_dev=dataset_a.orp_std_dev,
            variance=dataset_a.orp_variance,
            sharpe=dataset_a.orp_sharpe,
        )
        points = cal_points(orp, risk_free_rate=dataset_a.risk_free_rate, resolution=21)
        assert points[0].std_dev == pytest.approx(0.0)
        assert points[0].expected_return == pytest.approx(dataset_a.risk_free_rate)
        # Check the slope (Sharpe) along the line.
        for p in points[1:]:
            slope = (p.expected_return - dataset_a.risk_free_rate) / max(p.std_dev, 1e-12)
            assert slope == pytest.approx(dataset_a.orp_sharpe, abs=1e-9)

    def test_y_star_inside_range(self, dataset_a: DatasetAFixture) -> None:
        orp = ORP(
            weights=dict(dataset_a.orp_weights),
            expected_return=dataset_a.orp_expected_return,
            std_dev=dataset_a.orp_std_dev,
            variance=dataset_a.orp_variance,
            sharpe=dataset_a.orp_sharpe,
        )
        points = cal_points(
            orp,
            risk_free_rate=dataset_a.risk_free_rate,
            y_star=1.5625,
            resolution=21,
        )
        assert max(p.y for p in points) >= 1.5625

    def test_invalid_resolution_raises(self, dataset_a: DatasetAFixture) -> None:
        orp = ORP(
            weights=dict(dataset_a.orp_weights),
            expected_return=dataset_a.orp_expected_return,
            std_dev=dataset_a.orp_std_dev,
            variance=dataset_a.orp_variance,
            sharpe=dataset_a.orp_sharpe,
        )
        with pytest.raises(ValueError):
            cal_points(orp, risk_free_rate=0.04, resolution=1)

    def test_non_positive_std_raises(self) -> None:
        orp = ORP(
            weights={"X": 1.0},
            expected_return=0.1,
            std_dev=0.0,
            variance=0.0,
            sharpe=0.0,
        )
        with pytest.raises(ValueError):
            cal_points(orp, risk_free_rate=0.04, resolution=10)


def test_frontier_infeasible_discriminant() -> None:
    """If μ is a constant vector, B²/A² = C/A → D = 0 → OptimizerInfeasibleError."""
    mu = np.array([0.10, 0.10, 0.10])
    cov = np.diag([0.04, 0.09, 0.16])
    with pytest.raises(OptimizerInfeasibleError):
        efficient_frontier_points(mu, cov, frontier_resolution=20)
