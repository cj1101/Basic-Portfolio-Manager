"""Markowitz Optimal Risky Portfolio (ORP) / tangency portfolio.

Two code paths matching ``.cursor/rules/quant.mdc`` §3:

- **Unconstrained (``allow_short=True``, full-MPT default).** Closed form:
  ``w* ∝ Σ⁻¹(μ − rᶠ·𝟏)`` normalized to sum to 1. Byte-exact, no solver.
- **Long-only (``allow_short=False``).** QP solved with ``cvxpy``:

    maximize ``(μ − rᶠ)ᵀw`` subject to ``wᵀΣw ≤ 1``, ``w ≥ 0``,

  then renormalized so ``Σwᵢ = 1``. The objective is the Sharpe ratio up to
  positive rescaling (Cornuejols–Tütüncü transformation).

``allow_leverage`` does **not** change the ORP itself — the ORP weights
always sum to 1 per convention. Leverage is a downstream concern of
:func:`quant.allocation.utility_max_allocation`. The flag is accepted here
(and recorded) to match the uniform optimizer interface required by the
spec.

The function returns a fully populated :class:`quant.types.ORP`.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from numpy.typing import NDArray

from .errors import OptimizerInfeasibleError
from .linalg import ensure_psd_covariance
from .types import ORP

SUM_TOL: float = 1e-9


def _tangency_unconstrained(
    expected_returns: NDArray[np.float64],
    covariance: NDArray[np.float64],
    risk_free_rate: float,
) -> NDArray[np.float64]:
    excess = expected_returns - float(risk_free_rate)
    z = np.linalg.solve(covariance, excess)
    s = float(np.sum(z))
    if not np.isfinite(s) or abs(s) < 1e-14:
        raise OptimizerInfeasibleError(
            "tangency normalization is degenerate; Σ⁻¹(μ − rᶠ𝟏) sums to approximately zero",
            {"sum": s},
        )
    return np.asarray(z / s, dtype=np.float64)


def _tangency_long_only(
    expected_returns: NDArray[np.float64],
    covariance: NDArray[np.float64],
    risk_free_rate: float,
) -> NDArray[np.float64]:
    import cvxpy as cp

    n = expected_returns.shape[0]
    excess = expected_returns - float(risk_free_rate)

    if float(np.max(excess)) <= 0.0:
        raise OptimizerInfeasibleError(
            "no asset has positive excess return over the risk-free rate; "
            "long-only tangency is undefined",
            {"maxExcess": float(np.max(excess))},
        )

    w = cp.Variable(n, nonneg=True)
    problem = cp.Problem(
        cp.Maximize(excess @ w),
        [cp.quad_form(w, cp.psd_wrap(covariance)) <= 1.0],
    )
    try:
        problem.solve()
    except cp.error.SolverError as exc:  # pragma: no cover - solver-specific
        raise OptimizerInfeasibleError(
            "cvxpy solver raised during long-only tangency",
            {"error": str(exc)},
        ) from exc

    if problem.status not in {"optimal", "optimal_inaccurate"} or w.value is None:
        raise OptimizerInfeasibleError(
            "long-only tangency is infeasible or unbounded",
            {"status": str(problem.status)},
        )

    raw = np.asarray(w.value, dtype=np.float64).reshape(-1)
    raw = np.clip(raw, 0.0, None)
    s = float(raw.sum())
    if s <= SUM_TOL:
        raise OptimizerInfeasibleError(
            "long-only tangency produced a zero-weight vector",
            {"sum": s},
        )
    return raw / s


def optimize_markowitz(
    tickers: list[str],
    expected_returns: NDArray[np.float64] | list[float],
    covariance: NDArray[np.float64] | list[list[float]],
    risk_free_rate: float,
    allow_short: bool,
    allow_leverage: bool,
    warnings: list[str] | None = None,
) -> ORP:
    """Solve for the ORP (tangency portfolio)."""
    _ = allow_leverage  # spec §3: accepted uniformly even when unused in ORP selection.

    mu = np.asarray(expected_returns, dtype=np.float64).reshape(-1)
    cov_in = np.asarray(covariance, dtype=np.float64)
    if mu.shape[0] != len(tickers):
        raise ValueError(f"tickers length {len(tickers)} != expected_returns length {mu.shape[0]}")
    if cov_in.shape != (mu.shape[0], mu.shape[0]):
        raise ValueError(f"covariance must be ({mu.shape[0]},{mu.shape[0]}); got {cov_in.shape}")
    if not np.all(np.isfinite(mu)):
        raise OptimizerInfeasibleError(
            "expected_returns contain NaN or Inf", {"tickers": list(tickers)}
        )

    cov = ensure_psd_covariance(cov_in, warnings=warnings)

    weights_vec = (
        _tangency_unconstrained(mu, cov, float(risk_free_rate))
        if allow_short
        else _tangency_long_only(mu, cov, float(risk_free_rate))
    )

    w_sum = float(weights_vec.sum())
    if abs(w_sum - 1.0) > SUM_TOL:
        weights_vec = weights_vec / w_sum

    e_r = float(mu @ weights_vec)
    var = float(weights_vec @ cov @ weights_vec)
    if var <= 0.0:
        raise OptimizerInfeasibleError("ORP variance came out non-positive", {"variance": var})
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


def portfolio_weights_vector(tickers: list[str], weights: dict[str, float]) -> NDArray[np.float64]:
    """Helper: turn a ``dict[ticker, weight]`` into an ordered numpy vector.

    Raises :class:`KeyError` if a ticker is missing, preserving the explicit
    ordering required by ``.cursor/rules/quant.mdc`` §2.
    """
    return cast(
        "NDArray[np.float64]",
        np.asarray([float(weights[t]) for t in tickers], dtype=np.float64),
    )


__all__ = ["SUM_TOL", "optimize_markowitz", "portfolio_weights_vector"]
