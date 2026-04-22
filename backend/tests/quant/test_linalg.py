"""Tests for ``quant.linalg``."""

from __future__ import annotations

import numpy as np
import pytest

from quant.errors import OptimizerNonPSDCovarianceError
from quant.linalg import (
    PSD_TOL,
    SYMMETRY_TOL,
    build_covariance,
    covariance_to_correlation,
    ensure_psd_covariance,
    is_psd,
    is_symmetric,
    nearest_psd,
)

from ..conftest import TOLERANCE_SYMMETRY


class TestBuildCovariance:
    def test_diagonal_dataset_a(self) -> None:
        sigma = [0.15, 0.20, 0.30]
        rho = np.eye(3)
        expected = np.diag([0.0225, 0.04, 0.09])
        actual = build_covariance(sigma, rho)
        np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_non_diagonal(self) -> None:
        sigma = np.array([0.2, 0.3])
        rho = np.array([[1.0, 0.4], [0.4, 1.0]])
        cov = build_covariance(sigma, rho)
        assert cov[0, 0] == pytest.approx(0.04, abs=1e-12)
        assert cov[1, 1] == pytest.approx(0.09, abs=1e-12)
        assert cov[0, 1] == pytest.approx(0.2 * 0.3 * 0.4, abs=1e-12)
        assert cov[0, 1] == pytest.approx(cov[1, 0], abs=TOLERANCE_SYMMETRY)

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            build_covariance([0.1, 0.2], np.eye(3))

    def test_negative_std_dev_raises(self) -> None:
        with pytest.raises(ValueError):
            build_covariance([-0.1, 0.2], np.eye(2))


class TestCovarianceToCorrelation:
    def test_round_trip_with_build_covariance(self) -> None:
        sigma = np.array([0.15, 0.20, 0.30])
        rho_in = np.array([[1.0, 0.3, 0.1], [0.3, 1.0, 0.2], [0.1, 0.2, 1.0]])
        cov = build_covariance(sigma, rho_in)
        rho_out = covariance_to_correlation(cov)
        np.testing.assert_allclose(rho_out, rho_in, atol=1e-9)
        assert float(np.min(np.diag(rho_out))) == pytest.approx(1.0, abs=1e-12)

    def test_non_square_raises(self) -> None:
        with pytest.raises(ValueError, match="square"):
            covariance_to_correlation(np.zeros((2, 3)))

    def test_nonpositive_diagonal_raises(self) -> None:
        m = np.diag([0.04, -0.01])
        with pytest.raises(ValueError, match="positive"):
            covariance_to_correlation(m)


class TestIsSymmetricIsPSD:
    def test_identity_is_symmetric_and_psd(self) -> None:
        m = np.eye(4)
        assert is_symmetric(m)
        assert is_psd(m)

    def test_non_square_is_not_symmetric(self) -> None:
        m = np.zeros((2, 3))
        assert not is_symmetric(m)
        assert not is_psd(m)

    def test_asymmetric_detected(self) -> None:
        m = np.array([[1.0, 0.5], [0.0, 1.0]])
        assert not is_symmetric(m)

    def test_non_psd_detected(self) -> None:
        m = np.array([[1.0, 2.0], [2.0, 1.0]])
        assert is_symmetric(m)
        assert not is_psd(m)


class TestNearestPSD:
    def test_psd_matrix_passes_through(self) -> None:
        m = np.diag([0.0225, 0.04, 0.09])
        out = nearest_psd(m)
        np.testing.assert_allclose(out, m, atol=1e-12)

    def test_projects_small_negative_eigenvalue(self) -> None:
        base = np.diag([0.04, 0.09])
        perturbed = base.copy()
        perturbed[0, 0] = -1e-10
        out = nearest_psd(perturbed)
        eigvals = np.linalg.eigvalsh(out)
        assert float(np.min(eigvals)) >= 0.0
        np.testing.assert_allclose(out - out.T, 0.0, atol=TOLERANCE_SYMMETRY)

    def test_rejects_non_square(self) -> None:
        with pytest.raises(ValueError):
            nearest_psd(np.zeros((2, 3)))


class TestEnsurePSDCovariance:
    def test_clean_matrix_returns_symmetrized_copy(self) -> None:
        m = np.diag([0.0225, 0.04, 0.09])
        warnings: list[str] = []
        out = ensure_psd_covariance(m, warnings=warnings)
        np.testing.assert_allclose(out, m, atol=1e-12)
        assert warnings == []

    def test_minor_drift_projected_with_warning(self) -> None:
        m = np.diag([0.0225, 0.04, 0.09])
        m[0, 0] = -PSD_TOL / 2
        warnings: list[str] = []
        out = ensure_psd_covariance(m, warnings=warnings)
        assert len(warnings) == 1 and "projected to nearest PSD" in warnings[0]
        assert float(np.min(np.linalg.eigvalsh(out))) >= 0.0

    def test_large_negative_raises(self) -> None:
        m = np.array([[1.0, 2.0], [2.0, 1.0]])
        with pytest.raises(OptimizerNonPSDCovarianceError):
            ensure_psd_covariance(m)

    def test_non_symmetric_raises(self) -> None:
        m = np.array([[1.0, 0.5 + 10 * SYMMETRY_TOL], [0.5, 1.0]])
        with pytest.raises(OptimizerNonPSDCovarianceError):
            ensure_psd_covariance(m)

    def test_non_square_raises(self) -> None:
        with pytest.raises(OptimizerNonPSDCovarianceError):
            ensure_psd_covariance(np.zeros((2, 3)))
