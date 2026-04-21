"""Global minimum-variance portfolio (MVP).

- **Unconstrained (``allow_short=True``).** Closed form
  ``w = Σ⁻¹𝟏 / (𝟏ᵀΣ⁻¹𝟏)``.
- **Long-only (``allow_short=False``).** ``min wᵀΣw`` subject to
  ``Σwᵢ = 1``, ``w ≥ 0``; solved with ``cvxpy``.

Returned as an :class:`quant.types.ORP` for symmetry with
:func:`quant.markowitz.optimize_markowitz` — the Sharpe field is a valid
Sharpe at this particular ``(E(r), σ, rᶠ)``, but is usually smaller than the
ORP's.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .errors import OptimizerInfeasibleError
from .linalg import ensure_psd_covariance
from .types import ORP

SUM_TOL: float = 1e-9


def _mvp_unconstrained(covariance: NDArray[np.float64]) -> NDArray[np.float64]:
    n = covariance.shape[0]
    ones = np.ones(n, dtype=np.float64)
    z = np.linalg.solve(covariance, ones)
    s = float(np.sum(z))
    if not np.isfinite(s) or abs(s) < 1e-14:
        raise OptimizerInfeasibleError(
            "unconstrained MVP normalization is degenerate",
            {"sum": s},
        )
    return np.asarray(z / s, dtype=np.float64)


def _mvp_long_only(covariance: NDArray[np.float64]) -> NDArray[np.float64]:
    import cvxpy as cp

    n = covariance.shape[0]
    w = cp.Variable(n, nonneg=True)
    problem = cp.Problem(
        cp.Minimize(cp.quad_form(w, cp.psd_wrap(covariance))),
        [cp.sum(w) == 1.0],
    )
    try:
        problem.solve()
    except cp.error.SolverError as exc:  # pragma: no cover - solver-specific
        raise OptimizerInfeasibleError(
            "cvxpy solver raised during long-only MVP",
            {"error": str(exc)},
        ) from exc

    if problem.status not in {"optimal", "optimal_inaccurate"} or w.value is None:
        raise OptimizerInfeasibleError(
            "long-only MVP is infeasible or unbounded",
            {"status": str(problem.status)},
        )

    raw = np.asarray(w.value, dtype=np.float64).reshape(-1)
    raw = np.clip(raw, 0.0, None)
    s = float(raw.sum())
    if s <= SUM_TOL:
        raise OptimizerInfeasibleError(
            "long-only MVP produced a zero-weight vector",
            {"sum": s},
        )
    return raw / s


def minimum_variance_portfolio(
    tickers: list[str],
    expected_returns: NDArray[np.float64] | list[float],
    covariance: NDArray[np.float64] | list[list[float]],
    risk_free_rate: float,
    allow_short: bool,
    warnings: list[str] | None = None,
) -> ORP:
    """Solve for the global minimum-variance portfolio."""
    mu = np.asarray(expected_returns, dtype=np.float64).reshape(-1)
    cov_in = np.asarray(covariance, dtype=np.float64)
    if mu.shape[0] != len(tickers):
        raise ValueError(f"tickers length {len(tickers)} != expected_returns length {mu.shape[0]}")
    if cov_in.shape != (mu.shape[0], mu.shape[0]):
        raise ValueError(f"covariance must be ({mu.shape[0]},{mu.shape[0]}); got {cov_in.shape}")

    cov = ensure_psd_covariance(cov_in, warnings=warnings)

    weights_vec = _mvp_unconstrained(cov) if allow_short else _mvp_long_only(cov)

    w_sum = float(weights_vec.sum())
    if abs(w_sum - 1.0) > SUM_TOL:
        weights_vec = weights_vec / w_sum

    e_r = float(mu @ weights_vec)
    var = float(weights_vec @ cov @ weights_vec)
    if var <= 0.0:
        raise OptimizerInfeasibleError("MVP variance came out non-positive", {"variance": var})
    sd = float(np.sqrt(var))
    sharpe = (e_r - float(risk_free_rate)) / sd

    weights = {tickers[i]: float(weights_vec[i]) for i in range(len(tickers))}

    return ORP(
        weights=weights,
        expected_return=e_r,
        std_dev=sd,
        variance=var,
        sharpe=sharpe,
    )


__all__ = ["SUM_TOL", "minimum_variance_portfolio"]
