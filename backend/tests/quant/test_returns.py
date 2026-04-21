"""Tests for ``quant.returns``."""

from __future__ import annotations

import numpy as np
import pytest

from quant.errors import InsufficientHistoryError, InvalidReturnWindowError
from quant.returns import (
    ANNUALIZATION_FACTORS,
    annualization_factor,
    annualize_mean,
    annualize_std,
    annualize_variance,
    expected_returns,
    sample_covariance,
    std_devs,
)
from quant.types import ReturnFrequency


class TestAnnualization:
    @pytest.mark.parametrize(
        ("frequency", "factor"),
        [
            (ReturnFrequency.DAILY, 252),
            (ReturnFrequency.WEEKLY, 52),
            (ReturnFrequency.MONTHLY, 12),
        ],
    )
    def test_factor(self, frequency: ReturnFrequency, factor: int) -> None:
        assert annualization_factor(frequency) == factor

    def test_factor_map_exposed(self) -> None:
        assert ANNUALIZATION_FACTORS[ReturnFrequency.DAILY] == 252

    def test_annualize_mean(self) -> None:
        assert annualize_mean(0.001, ReturnFrequency.DAILY) == pytest.approx(0.252)

    def test_annualize_std(self) -> None:
        assert annualize_std(0.01, ReturnFrequency.DAILY) == pytest.approx(
            0.01 * np.sqrt(252)
        )

    def test_annualize_variance(self) -> None:
        assert annualize_variance(0.0001, ReturnFrequency.DAILY) == pytest.approx(0.0252)


class TestExpectedReturns:
    def test_constant_returns(self) -> None:
        t = 252
        r = np.full((t, 3), 0.0004)
        mu = expected_returns(r, ReturnFrequency.DAILY)
        np.testing.assert_allclose(mu, [0.0004 * 252] * 3, atol=1e-12)

    def test_one_observation_raises(self) -> None:
        with pytest.raises(InsufficientHistoryError):
            expected_returns(np.zeros((1, 3)), ReturnFrequency.DAILY)

    def test_one_dim_raises(self) -> None:
        with pytest.raises(InvalidReturnWindowError):
            expected_returns(np.zeros(5), ReturnFrequency.DAILY)

    def test_non_finite_raises(self) -> None:
        r = np.zeros((10, 2))
        r[0, 0] = np.nan
        with pytest.raises(InvalidReturnWindowError):
            expected_returns(r, ReturnFrequency.DAILY)


class TestStdDevsAndCovariance:
    def test_std_devs_match_manual(self) -> None:
        rng = np.random.default_rng(42)
        r = rng.normal(scale=0.01, size=(500, 3))
        sd = std_devs(r, ReturnFrequency.DAILY)
        expected = r.std(axis=0, ddof=1) * np.sqrt(252)
        np.testing.assert_allclose(sd, expected, atol=1e-12)

    def test_sample_covariance_symmetric_and_psd(self) -> None:
        rng = np.random.default_rng(7)
        r = rng.normal(scale=0.01, size=(500, 3))
        cov = sample_covariance(r, ReturnFrequency.DAILY)
        np.testing.assert_allclose(cov, cov.T, atol=1e-12)
        eig = np.linalg.eigvalsh(cov)
        assert float(np.min(eig)) >= -1e-10
