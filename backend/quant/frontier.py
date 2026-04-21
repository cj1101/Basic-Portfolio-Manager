"""Efficient frontier (Markowitz hyperbola) and Capital Allocation Line.

Both helpers are pure: they take already-validated inputs and emit lists of
:class:`quant.types.FrontierPoint` / :class:`quant.types.CALPoint`.

Closed-form frontier (Merton 1972) for the full-MPT case (shorts allowed):

::

    A = 𝟏ᵀ Σ⁻¹ 𝟏
    B = 𝟏ᵀ Σ⁻¹ μ
    C = μᵀ Σ⁻¹ μ
    D = A·C − B²

For any target return ``μ*``, the minimum variance achievable subject to
``Σwᵢ = 1`` is ``σ²(μ*) = (A·μ*² − 2·B·μ* + C) / D``, and the efficient
branch is ``μ* ≥ μ_MVP = B / A``. This generates the frontier directly
without a solver.

For the long-only case (``allow_short=False``) we'd need per-target QPs —
out of scope for Phase 1A except as a follow-up flag; in that case we fall
back to the unconstrained Merton curve with a warning.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from .errors import OptimizerInfeasibleError
from .linalg import ensure_psd_covariance
from .types import ORP, CALPoint, FrontierPoint

DISCRIMINANT_TOL: float = 1e-12
"""Floor on the Merton discriminant ``D = A·C − B²`` below which the frontier
is considered degenerate."""


def efficient_frontier_points(
    expected_returns: NDArray[np.float64] | list[float],
    covariance: NDArray[np.float64] | list[list[float]],
    frontier_resolution: int = 40,
    upper_return_extension: float = 1.5,
    warnings: list[str] | None = None,
) -> list[FrontierPoint]:
    """Sample the Markowitz efficient frontier (full-MPT, shorts allowed).

    ``frontier_resolution``: number of returned points (≥ 5).
    ``upper_return_extension``: how far above ``max(μ)`` the sweep reaches,
    as a multiplicative factor of ``max(μ) − μ_MVP`` (default 1.5).
    """
    if frontier_resolution < 5:
        raise ValueError(f"frontier_resolution must be ≥ 5; got {frontier_resolution}")

    mu = np.asarray(expected_returns, dtype=np.float64).reshape(-1)
    cov = ensure_psd_covariance(np.asarray(covariance, dtype=np.float64), warnings=warnings)

    ones = np.ones(mu.shape[0], dtype=np.float64)
    inv_cov_ones = np.linalg.solve(cov, ones)
    inv_cov_mu = np.linalg.solve(cov, mu)

    a_const = float(ones @ inv_cov_ones)
    b_const = float(ones @ inv_cov_mu)
    c_const = float(mu @ inv_cov_mu)
    d_const = a_const * c_const - b_const * b_const

    if d_const <= DISCRIMINANT_TOL or a_const <= 0.0:
        raise OptimizerInfeasibleError(
            "frontier discriminant is non-positive; inputs are degenerate",
            {"A": a_const, "B": b_const, "C": c_const, "D": d_const},
        )

    mu_mvp = b_const / a_const
    mu_top = float(np.max(mu))
    span = max(mu_top - mu_mvp, 1e-9)
    mu_upper = mu_top + upper_return_extension * span

    targets = np.linspace(mu_mvp, mu_upper, frontier_resolution)

    points: list[FrontierPoint] = []
    for mu_target in targets:
        variance = (a_const * mu_target * mu_target - 2.0 * b_const * mu_target + c_const) / d_const
        if variance < 0.0:
            continue
        points.append(
            FrontierPoint(
                std_dev=float(math.sqrt(variance)),
                expected_return=float(mu_target),
            )
        )
    return points


def cal_points(
    orp: ORP,
    risk_free_rate: float,
    y_star: float | None = None,
    resolution: int = 21,
    margin: float = 0.5,
) -> list[CALPoint]:
    """Sample the Capital Allocation Line from (0, rᶠ) out to beyond y*.

    The CAL is the straight line ``E(r)(y) = rᶠ + y·(E(r_ORP) − rᶠ)`` with
    ``σ(y) = y·σ_ORP``. When ``y_star`` is supplied, the upper bound is
    ``max(1, y_star) + margin`` so the complete-portfolio point always lies
    inside the sampled range.
    """
    if resolution < 2:
        raise ValueError(f"resolution must be ≥ 2; got {resolution}")
    rf = float(risk_free_rate)
    excess = float(orp.expected_return) - rf
    sd_orp = float(orp.std_dev)
    if sd_orp <= 0.0:
        raise ValueError(f"orp.std_dev must be > 0; got {sd_orp}")

    y_top = 1.0 if y_star is None else max(1.0, float(y_star))
    y_max = y_top + float(margin)
    ys = np.linspace(0.0, y_max, resolution)

    return [
        CALPoint(
            std_dev=float(y * sd_orp),
            expected_return=float(rf + y * excess),
            y=float(y),
        )
        for y in ys
    ]


__all__ = ["DISCRIMINANT_TOL", "cal_points", "efficient_frontier_points"]
