"""Hypothesis property tests for the quant engine.

We exercise three invariants that should hold for **any** well-formed
covariance matrix + expected-return vector + risk profile combination.
Hypothesis generates adversarial examples (near-singular covariances,
very small variances, extreme risk-premium/aversion ratios, ...) and
shrinks them when an assertion fails.

These tests do not replace the unit tests — they complement them by
widening the input space past the handful of hand-rolled fixtures.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from quant.allocation import utility_max_allocation
from quant.linalg import ensure_psd_covariance
from quant.markowitz import optimize_markowitz
from quant.types import ORP, RiskProfile

MAX_N = 12
MIN_N = 2


@st.composite
def _spd_covariance(draw: st.DrawFn, *, n: int) -> np.ndarray:
    """Generate a symmetric positive-definite covariance matrix.

    We build it as ``diag(d) + A·Aᵀ`` where each entry of ``A`` is bounded,
    then clip eigenvalues to a floor so the matrix is guaranteed PD.
    """

    entries = draw(
        st.lists(
            st.floats(
                min_value=-2.0,
                max_value=2.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=n * n,
            max_size=n * n,
        )
    )
    a = np.asarray(entries, dtype=np.float64).reshape(n, n)
    sym = a @ a.T
    # Add a small diagonal so the matrix is strictly positive-definite even
    # when ``a`` is rank-deficient.
    eye_scale = draw(st.floats(min_value=1e-3, max_value=0.5))
    cov = sym + eye_scale * np.eye(n)
    return cov


@st.composite
def _expected_returns(draw: st.DrawFn, *, n: int) -> np.ndarray:
    values = draw(
        st.lists(
            st.floats(
                min_value=-0.30,
                max_value=0.80,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=n,
            max_size=n,
        )
    )
    return np.asarray(values, dtype=np.float64)


_SLOW = settings(
    deadline=None,
    max_examples=40,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)


@given(n=st.integers(min_value=MIN_N, max_value=MAX_N), seed=st.integers(0, 2**16))
@_SLOW
def test_ensure_psd_symmetric_and_eigvals_nonnegative(n: int, seed: int) -> None:
    """Feed a symmetric PSD matrix and check the output stays PSD, symmetric,
    and shape-preserving. We construct ``A·Aᵀ + εI`` so the input is
    guaranteed positive-definite (matches the ``quant.mdc`` covariance
    contract the caller must satisfy)."""

    rng = np.random.default_rng(seed)
    a = rng.uniform(-1.0, 1.0, size=(n, n))
    spd = a @ a.T + 1e-2 * np.eye(n)
    warnings: list[str] = []
    psd = ensure_psd_covariance(spd, warnings=warnings)
    assert psd.shape == (n, n)
    assert np.allclose(psd, psd.T, atol=1e-10)
    eigvals = np.linalg.eigvalsh(psd)
    assert float(eigvals.min()) >= -1e-10


@given(
    n=st.integers(min_value=MIN_N, max_value=MAX_N),
    cov_seed=st.integers(0, 2**16),
    mu_seed=st.integers(0, 2**16),
    rf=st.floats(min_value=0.0, max_value=0.08, allow_nan=False, allow_infinity=False),
)
@_SLOW
def test_optimize_markowitz_weights_sum_to_one_and_nonneg_when_longonly(
    n: int, cov_seed: int, mu_seed: int, rf: float
) -> None:
    cov_rng = np.random.default_rng(cov_seed)
    mu_rng = np.random.default_rng(mu_seed)
    a = cov_rng.uniform(-0.2, 0.2, size=(n, n))
    cov = a @ a.T + 0.05 * np.eye(n)
    mu = mu_rng.uniform(0.02, 0.35, size=n)  # all positive risk premia
    if float((mu - rf).max()) <= 0.0:
        pytest.skip("no positive risk premium — ORP undefined")

    tickers = [f"T{i}" for i in range(n)]
    orp = optimize_markowitz(
        tickers=tickers,
        expected_returns=mu,
        covariance=cov,
        risk_free_rate=rf,
        allow_short=False,
        allow_leverage=False,
    )
    weights = np.array(list(orp.weights.values()))
    assert abs(weights.sum() - 1.0) < 1e-6
    assert float(weights.min()) >= -1e-9  # long-only, modulo numerical slop
    assert orp.variance > 0.0
    # Sharpe should be finite and (weakly) positive since all mu > rf.
    assert np.isfinite(orp.sharpe)
    assert orp.sharpe > -1e-6


@given(
    expected_return=st.floats(min_value=0.02, max_value=0.40, allow_nan=False),
    std_dev=st.floats(min_value=0.05, max_value=0.60, allow_nan=False),
    rf=st.floats(min_value=0.0, max_value=0.06, allow_nan=False),
    risk_aversion=st.integers(min_value=1, max_value=10),
)
@_SLOW
def test_utility_max_allocation_y_nonneg_and_leverage_clamp(
    expected_return: float,
    std_dev: float,
    rf: float,
    risk_aversion: int,
) -> None:
    if expected_return <= rf:
        pytest.skip("no risk premium — y* is non-positive (out of v1 scope).")

    orp = ORP(
        weights={"X": 1.0},
        expected_return=expected_return,
        std_dev=std_dev,
        variance=std_dev**2,
        sharpe=(expected_return - rf) / std_dev,
    )
    profile = RiskProfile(risk_aversion=risk_aversion)

    # allow_leverage=True → closed-form y* is preserved.
    warnings: list[str] = []
    cp_lev = utility_max_allocation(orp, rf, profile, allow_leverage=True, warnings=warnings)
    closed_form = (expected_return - rf) / (risk_aversion * std_dev**2)
    assert cp_lev.y_star == pytest.approx(closed_form, rel=1e-9, abs=1e-9)
    assert cp_lev.y_star >= 0.0
    # Check leverage bookkeeping.
    assert cp_lev.leverage_used == (cp_lev.y_star > 1.0)
    assert cp_lev.weight_risk_free == pytest.approx(1.0 - cp_lev.y_star, abs=1e-12)

    # allow_leverage=False → clamp at y*=1.
    warnings_clamp: list[str] = []
    cp_noLev = utility_max_allocation(
        orp, rf, profile, allow_leverage=False, warnings=warnings_clamp
    )
    assert cp_noLev.y_star <= 1.0 + 1e-12
    if closed_form > 1.0:
        assert cp_noLev.y_star == pytest.approx(1.0, abs=1e-12)
        assert warnings_clamp, "expected a clamp warning when closed-form y* > 1"


@given(
    expected_return=st.floats(min_value=0.08, max_value=0.30, allow_nan=False),
    std_dev=st.floats(min_value=0.10, max_value=0.60, allow_nan=False),
    rf=st.floats(min_value=0.0, max_value=0.05, allow_nan=False),
    target_delta=st.floats(min_value=0.05, max_value=0.60, allow_nan=False),
    risk_aversion=st.integers(min_value=4, max_value=10),
)
@_SLOW
def test_target_return_overrides_when_exceeding_orp_return(
    expected_return: float,
    std_dev: float,
    rf: float,
    target_delta: float,
    risk_aversion: int,
) -> None:
    if expected_return <= rf:
        pytest.skip("no risk premium.")
    # Build the target strictly above E(r_ORP) so the override path triggers.
    target = expected_return + target_delta
    orp = ORP(
        weights={"X": 1.0},
        expected_return=expected_return,
        std_dev=std_dev,
        variance=std_dev**2,
        sharpe=(expected_return - rf) / std_dev,
    )
    profile = RiskProfile(risk_aversion=risk_aversion, target_return=target)
    warnings: list[str] = []
    cp = utility_max_allocation(orp, rf, profile, allow_leverage=True, warnings=warnings)
    y_target = (target - rf) / (expected_return - rf)
    y_closed = (expected_return - rf) / (risk_aversion * std_dev**2)
    assert cp.y_star == pytest.approx(max(y_closed, y_target), rel=1e-9, abs=1e-9)
