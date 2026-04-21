"""Tests for ``quant.markowitz``."""

from __future__ import annotations

import numpy as np
import pytest

from quant.errors import OptimizerInfeasibleError, OptimizerNonPSDCovarianceError
from quant.markowitz import optimize_markowitz, portfolio_weights_vector

from ..conftest import DatasetAFixture, TOLERANCE_SCALAR, TOLERANCE_WEIGHT_SUM


class TestDatasetAUnconstrained:
    def test_weights(self, dataset_a: DatasetAFixture) -> None:
        orp = optimize_markowitz(
            list(dataset_a.tickers),
            dataset_a.expected_returns,
            dataset_a.covariance,
            risk_free_rate=dataset_a.risk_free_rate,
            allow_short=True,
            allow_leverage=True,
        )
        for ticker, expected in dataset_a.orp_weights.items():
            assert orp.weights[ticker] == pytest.approx(expected, abs=TOLERANCE_SCALAR)

    def test_weight_sum(self, dataset_a: DatasetAFixture) -> None:
        orp = optimize_markowitz(
            list(dataset_a.tickers),
            dataset_a.expected_returns,
            dataset_a.covariance,
            risk_free_rate=dataset_a.risk_free_rate,
            allow_short=True,
            allow_leverage=True,
        )
        assert sum(orp.weights.values()) == pytest.approx(1.0, abs=TOLERANCE_WEIGHT_SUM)

    def test_moments_and_sharpe(self, dataset_a: DatasetAFixture) -> None:
        orp = optimize_markowitz(
            list(dataset_a.tickers),
            dataset_a.expected_returns,
            dataset_a.covariance,
            risk_free_rate=dataset_a.risk_free_rate,
            allow_short=True,
            allow_leverage=True,
        )
        assert orp.expected_return == pytest.approx(
            dataset_a.orp_expected_return, abs=TOLERANCE_SCALAR
        )
        assert orp.std_dev == pytest.approx(dataset_a.orp_std_dev, abs=TOLERANCE_SCALAR)
        assert orp.variance == pytest.approx(dataset_a.orp_variance, abs=TOLERANCE_SCALAR)
        assert orp.sharpe == pytest.approx(dataset_a.orp_sharpe, abs=TOLERANCE_SCALAR)


class TestDatasetALongOnly:
    """For Dataset A, all stocks have a positive excess return, so the
    unconstrained tangency already lives in the positive orthant. The
    long-only solver must reproduce the same weights up to solver tolerance.
    """

    def test_matches_unconstrained_on_dataset_a(self, dataset_a: DatasetAFixture) -> None:
        orp = optimize_markowitz(
            list(dataset_a.tickers),
            dataset_a.expected_returns,
            dataset_a.covariance,
            risk_free_rate=dataset_a.risk_free_rate,
            allow_short=False,
            allow_leverage=True,
        )
        for ticker, expected in dataset_a.orp_weights.items():
            assert orp.weights[ticker] == pytest.approx(expected, abs=1e-4)
        assert all(w >= -1e-9 for w in orp.weights.values())
        assert orp.sharpe == pytest.approx(dataset_a.orp_sharpe, abs=1e-4)

    def test_no_positive_excess_is_infeasible(self) -> None:
        tickers = ["A", "B"]
        mu = np.array([0.01, 0.02])
        cov = np.diag([0.04, 0.09])
        with pytest.raises(OptimizerInfeasibleError):
            optimize_markowitz(
                tickers,
                mu,
                cov,
                risk_free_rate=0.05,
                allow_short=False,
                allow_leverage=True,
            )


class TestShapeValidation:
    def test_ticker_length_mismatch(self, dataset_a: DatasetAFixture) -> None:
        with pytest.raises(ValueError):
            optimize_markowitz(
                ["S1", "S2"],
                dataset_a.expected_returns,
                dataset_a.covariance,
                risk_free_rate=dataset_a.risk_free_rate,
                allow_short=True,
                allow_leverage=True,
            )

    def test_covariance_shape_mismatch(self, dataset_a: DatasetAFixture) -> None:
        with pytest.raises(ValueError):
            optimize_markowitz(
                list(dataset_a.tickers),
                dataset_a.expected_returns,
                np.eye(2),
                risk_free_rate=dataset_a.risk_free_rate,
                allow_short=True,
                allow_leverage=True,
            )

    def test_non_finite_mu_raises(self, dataset_a: DatasetAFixture) -> None:
        mu = dataset_a.expected_returns.copy()
        mu[0] = np.nan
        with pytest.raises(OptimizerInfeasibleError):
            optimize_markowitz(
                list(dataset_a.tickers),
                mu,
                dataset_a.covariance,
                risk_free_rate=dataset_a.risk_free_rate,
                allow_short=True,
                allow_leverage=True,
            )

    def test_non_psd_covariance_raises(self, dataset_a: DatasetAFixture) -> None:
        bad_cov = np.array([[1.0, 2.0, 0.0], [2.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        with pytest.raises(OptimizerNonPSDCovarianceError):
            optimize_markowitz(
                list(dataset_a.tickers),
                dataset_a.expected_returns,
                bad_cov,
                risk_free_rate=dataset_a.risk_free_rate,
                allow_short=True,
                allow_leverage=True,
            )


class TestPortfolioWeightsVector:
    def test_roundtrip(self) -> None:
        tickers = ["B", "A"]
        weights = {"A": 0.25, "B": 0.75}
        vec = portfolio_weights_vector(tickers, weights)
        np.testing.assert_array_equal(vec, np.array([0.75, 0.25]))

    def test_missing_ticker_raises(self) -> None:
        with pytest.raises(KeyError):
            portfolio_weights_vector(["A", "B"], {"A": 1.0})
