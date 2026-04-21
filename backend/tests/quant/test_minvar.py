"""Tests for ``quant.minvar``."""

from __future__ import annotations

import numpy as np
import pytest

from quant.minvar import minimum_variance_portfolio

from ..conftest import DatasetAFixture, TOLERANCE_SCALAR, TOLERANCE_WEIGHT_SUM


class TestDatasetAUnconstrained:
    def test_weights(self, dataset_a: DatasetAFixture) -> None:
        mvp = minimum_variance_portfolio(
            list(dataset_a.tickers),
            dataset_a.expected_returns,
            dataset_a.covariance,
            risk_free_rate=dataset_a.risk_free_rate,
            allow_short=True,
        )
        for ticker, expected in dataset_a.mvp_weights.items():
            assert mvp.weights[ticker] == pytest.approx(expected, abs=TOLERANCE_SCALAR)
        assert sum(mvp.weights.values()) == pytest.approx(1.0, abs=TOLERANCE_WEIGHT_SUM)

    def test_moments(self, dataset_a: DatasetAFixture) -> None:
        mvp = minimum_variance_portfolio(
            list(dataset_a.tickers),
            dataset_a.expected_returns,
            dataset_a.covariance,
            risk_free_rate=dataset_a.risk_free_rate,
            allow_short=True,
        )
        assert mvp.expected_return == pytest.approx(
            dataset_a.mvp_expected_return, abs=TOLERANCE_SCALAR
        )
        assert mvp.std_dev == pytest.approx(dataset_a.mvp_std_dev, abs=TOLERANCE_SCALAR)
        assert mvp.variance == pytest.approx(dataset_a.mvp_variance, abs=TOLERANCE_SCALAR)


class TestDatasetALongOnly:
    def test_matches_unconstrained_on_dataset_a(self, dataset_a: DatasetAFixture) -> None:
        mvp = minimum_variance_portfolio(
            list(dataset_a.tickers),
            dataset_a.expected_returns,
            dataset_a.covariance,
            risk_free_rate=dataset_a.risk_free_rate,
            allow_short=False,
        )
        for ticker, expected in dataset_a.mvp_weights.items():
            assert mvp.weights[ticker] == pytest.approx(expected, abs=1e-4)
        assert all(w >= -1e-9 for w in mvp.weights.values())

    def test_long_only_matches_closed_form_diagonal(self) -> None:
        tickers = ["X", "Y"]
        mu = np.array([0.05, 0.10])
        cov = np.diag([0.04, 0.09])
        mvp = minimum_variance_portfolio(
            tickers,
            mu,
            cov,
            risk_free_rate=0.04,
            allow_short=False,
        )
        expected = {"X": 9.0 / 13.0, "Y": 4.0 / 13.0}
        for t, w in expected.items():
            assert mvp.weights[t] == pytest.approx(w, abs=1e-4)


class TestValidation:
    def test_length_mismatch_raises(self, dataset_a: DatasetAFixture) -> None:
        with pytest.raises(ValueError):
            minimum_variance_portfolio(
                ["S1"],
                dataset_a.expected_returns,
                dataset_a.covariance,
                risk_free_rate=0.04,
                allow_short=True,
            )

    def test_covariance_shape_raises(self, dataset_a: DatasetAFixture) -> None:
        with pytest.raises(ValueError):
            minimum_variance_portfolio(
                list(dataset_a.tickers),
                dataset_a.expected_returns,
                np.eye(2),
                risk_free_rate=0.04,
                allow_short=True,
            )
