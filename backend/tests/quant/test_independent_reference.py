"""Phase 2 — independent reference implementation for ORP/tangency accuracy.

Validates the ``quant.markowitz.optimize_markowitz`` output against a
dependency-free linear-algebra reference (``np.linalg.solve``), covering:

- Dataset A (3-stock diagonal covariance)
- Dataset C (4-stock non-diagonal covariance)
- 5 seeded random problems (seeds 0–4, n=4 stocks)
- Long-only optimality invariants
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from quant.markowitz import optimize_markowitz

from ..conftest import TOLERANCE_SCALAR, DatasetAFixture, DatasetCFixture

# ---------------------------------------------------------------------------
# Reference implementations (no cvxpy, no optimizer)
# ---------------------------------------------------------------------------


def _reference_tangency(
    mu: NDArray[np.float64],
    cov: NDArray[np.float64],
    rf: float,
) -> NDArray[np.float64]:
    """Unconstrained tangency via Σ⁻¹(μ−rf·1), normalized. No cvxpy."""
    excess = mu - rf
    w_raw = np.linalg.solve(cov, excess)
    return w_raw / w_raw.sum()


def _reference_orp_moments(
    w: NDArray[np.float64],
    mu: NDArray[np.float64],
    cov: NDArray[np.float64],
    rf: float,
) -> tuple[float, float, float, float]:
    """Returns (expected_return, variance, std_dev, sharpe)."""
    er = float(w @ mu)
    var = float(w @ cov @ w)
    sd = float(np.sqrt(var))
    sharpe = (er - rf) / sd
    return er, var, sd, sharpe


# ---------------------------------------------------------------------------
# Test group 1 — Dataset A (3-stock diagonal covariance)
# ---------------------------------------------------------------------------


class TestDatasetAReference:
    def test_reference_weights_match_fixture(self, dataset_a: DatasetAFixture) -> None:
        w_ref = _reference_tangency(
            dataset_a.expected_returns,
            dataset_a.covariance,
            dataset_a.risk_free_rate,
        )
        for i, ticker in enumerate(dataset_a.tickers):
            assert w_ref[i] == pytest.approx(
                dataset_a.orp_weights[ticker], abs=TOLERANCE_SCALAR
            )

    def test_reference_moments_match_fixture(self, dataset_a: DatasetAFixture) -> None:
        w_ref = _reference_tangency(
            dataset_a.expected_returns,
            dataset_a.covariance,
            dataset_a.risk_free_rate,
        )
        er, var, sd, sharpe = _reference_orp_moments(
            w_ref,
            dataset_a.expected_returns,
            dataset_a.covariance,
            dataset_a.risk_free_rate,
        )
        assert er == pytest.approx(dataset_a.orp_expected_return, abs=TOLERANCE_SCALAR)
        assert var == pytest.approx(dataset_a.orp_variance, abs=TOLERANCE_SCALAR)
        assert sd == pytest.approx(dataset_a.orp_std_dev, abs=TOLERANCE_SCALAR)
        assert sharpe == pytest.approx(dataset_a.orp_sharpe, abs=TOLERANCE_SCALAR)

    def test_reference_matches_optimizer(self, dataset_a: DatasetAFixture) -> None:
        w_ref = _reference_tangency(
            dataset_a.expected_returns,
            dataset_a.covariance,
            dataset_a.risk_free_rate,
        )
        orp = optimize_markowitz(
            list(dataset_a.tickers),
            dataset_a.expected_returns,
            dataset_a.covariance,
            risk_free_rate=dataset_a.risk_free_rate,
            allow_short=True,
            allow_leverage=True,
        )
        for i, ticker in enumerate(dataset_a.tickers):
            assert orp.weights[ticker] == pytest.approx(w_ref[i], abs=TOLERANCE_SCALAR)


# ---------------------------------------------------------------------------
# Test group 2 — Dataset C (4-stock non-diagonal covariance)
# ---------------------------------------------------------------------------


class TestDatasetCReference:
    def test_reference_weights_match_fixture(self, dataset_c: DatasetCFixture) -> None:
        w_ref = _reference_tangency(dataset_c.mu, dataset_c.cov, dataset_c.rf)
        np.testing.assert_allclose(w_ref, dataset_c.w_tangency, atol=TOLERANCE_SCALAR)

    def test_reference_moments_match_fixture(self, dataset_c: DatasetCFixture) -> None:
        w_ref = _reference_tangency(dataset_c.mu, dataset_c.cov, dataset_c.rf)
        er, var, sd, sharpe = _reference_orp_moments(
            w_ref, dataset_c.mu, dataset_c.cov, dataset_c.rf
        )
        assert er == pytest.approx(dataset_c.er_orp, abs=TOLERANCE_SCALAR)
        assert var == pytest.approx(dataset_c.var_orp, abs=TOLERANCE_SCALAR)
        assert sd == pytest.approx(dataset_c.sd_orp, abs=TOLERANCE_SCALAR)
        assert sharpe == pytest.approx(dataset_c.sharpe_orp, abs=TOLERANCE_SCALAR)

    def test_reference_matches_optimizer(self, dataset_c: DatasetCFixture) -> None:
        w_ref = _reference_tangency(dataset_c.mu, dataset_c.cov, dataset_c.rf)
        orp = optimize_markowitz(
            list(dataset_c.tickers),
            dataset_c.mu,
            dataset_c.cov,
            risk_free_rate=dataset_c.rf,
            allow_short=True,
            allow_leverage=True,
        )
        for i, ticker in enumerate(dataset_c.tickers):
            assert orp.weights[ticker] == pytest.approx(w_ref[i], abs=TOLERANCE_SCALAR)


# ---------------------------------------------------------------------------
# Test group 3 — 5 seeded random problems (seeds 0–4, n=4)
# ---------------------------------------------------------------------------

_RANDOM_TOLERANCE: float = 1e-4


@pytest.mark.parametrize("seed", range(5))
def test_random_seeded(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = 4
    mu = rng.uniform(0.05, 0.25, n)
    A = rng.standard_normal((n, n))
    cov = (A @ A.T) / n + np.eye(n) * 0.01
    rf = 0.03

    tickers = [f"S{i + 1}" for i in range(n)]
    w_ref = _reference_tangency(mu, cov, rf)
    orp = optimize_markowitz(
        tickers,
        mu,
        cov,
        risk_free_rate=rf,
        allow_short=True,
        allow_leverage=True,
    )
    for i, ticker in enumerate(tickers):
        assert orp.weights[ticker] == pytest.approx(
            w_ref[i], abs=_RANDOM_TOLERANCE
        ), f"seed={seed}, ticker={ticker}"


# ---------------------------------------------------------------------------
# Test group 4 — Long-only optimality invariants
# ---------------------------------------------------------------------------


def _long_only_sharpe_dominates(
    mu: NDArray[np.float64],
    cov: NDArray[np.float64],
    rf: float,
    tickers: list[str],
) -> None:
    """Assert ORP Sharpe ≥ equal-weight Sharpe and ≥ every single-stock Sharpe."""
    orp = optimize_markowitz(
        tickers,
        mu,
        cov,
        risk_free_rate=rf,
        allow_short=False,
        allow_leverage=True,
    )

    n = len(tickers)
    w_eq = np.ones(n) / n
    er_eq = float(w_eq @ mu)
    sd_eq = float(np.sqrt(float(w_eq @ cov @ w_eq)))
    sharpe_eq = (er_eq - rf) / sd_eq
    assert orp.sharpe >= sharpe_eq - 1e-6, (
        f"ORP Sharpe {orp.sharpe:.6f} < equal-weight Sharpe {sharpe_eq:.6f}"
    )

    for i in range(n):
        sd_i = float(np.sqrt(cov[i, i]))
        sharpe_i = (float(mu[i]) - rf) / sd_i
        assert orp.sharpe >= sharpe_i - 1e-6, (
            f"ORP Sharpe {orp.sharpe:.6f} < stock {tickers[i]} Sharpe {sharpe_i:.6f}"
        )


class TestLongOnlyOptimalityInvariants:
    def test_dataset_a(self, dataset_a: DatasetAFixture) -> None:
        _long_only_sharpe_dominates(
            dataset_a.expected_returns,
            dataset_a.covariance,
            dataset_a.risk_free_rate,
            list(dataset_a.tickers),
        )

    def test_dataset_c(self, dataset_c: DatasetCFixture) -> None:
        _long_only_sharpe_dominates(
            dataset_c.mu,
            dataset_c.cov,
            dataset_c.rf,
            list(dataset_c.tickers),
        )

    def test_seed_0(self) -> None:
        rng = np.random.default_rng(0)
        n = 4
        mu = rng.uniform(0.05, 0.25, n)
        A = rng.standard_normal((n, n))
        cov = (A @ A.T) / n + np.eye(n) * 0.01
        rf = 0.03
        tickers = [f"S{i + 1}" for i in range(n)]
        _long_only_sharpe_dominates(mu, cov, rf, tickers)
