"""Single-Index Model (SIM).

Per-asset ``(α, β, σ²(e))`` estimated by OLS regression of asset excess
returns on market excess returns over the same window (``.cursor/rules/quant.mdc``
§5):

- ``β = Cov(r_i, r_M) / Var(r_M)``
- ``α = mean(excess_i) − β · mean(excess_M)``
- ``σ²(e_i) = Var(r_i) − β² · Var(r_M)``

Inputs are per-period return series (same frequency, same length). Outputs
are per-period scalars; the caller decides whether to annualize ``α`` and
``σ²(e)``. ``β`` is unitless and frequency-invariant.

If numerical drift causes ``σ²(e)`` to come out within ``[−1e-8, 0)`` it is
clamped to 0 with a warning (per rules §5). Anything more negative is raised
as a :class:`ValueError` because it indicates a real bug upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .errors import InsufficientHistoryError, InvalidReturnWindowError

CLAMP_FIRM_VAR_TOL: float = 1e-8


@dataclass(frozen=True)
class SingleIndexFit:
    """Per-asset regression output.

    ``alpha_per_period`` and ``firm_specific_var_per_period`` are in the units
    of the supplied return series. Beta is unitless.
    """

    alpha_per_period: float
    beta: float
    firm_specific_var_per_period: float
    n_observations: int


def single_index_metrics(
    returns_i: NDArray[np.float64] | list[float],
    returns_m: NDArray[np.float64] | list[float],
    risk_free_per_period: float = 0.0,
    warnings: list[str] | None = None,
) -> SingleIndexFit:
    """OLS fit of ``r_i − rᶠ = α + β · (r_M − rᶠ) + e``."""
    r_i = np.asarray(returns_i, dtype=np.float64).reshape(-1)
    r_m = np.asarray(returns_m, dtype=np.float64).reshape(-1)
    if r_i.shape != r_m.shape:
        raise InvalidReturnWindowError(
            "returns_i and returns_m must have matching shapes",
            {"shape_i": list(r_i.shape), "shape_m": list(r_m.shape)},
        )
    n = int(r_i.shape[0])
    if n < 2:
        raise InsufficientHistoryError(
            "need at least 2 observations for single-index regression",
            {"nObservations": n},
        )
    if not (np.all(np.isfinite(r_i)) and np.all(np.isfinite(r_m))):
        raise InvalidReturnWindowError("returns contain NaN or Inf")

    excess_i = r_i - float(risk_free_per_period)
    excess_m = r_m - float(risk_free_per_period)

    var_m = float(np.var(excess_m, ddof=1))
    if var_m <= 0.0:
        raise InvalidReturnWindowError(
            "market excess returns have zero variance; cannot fit beta",
            {"marketVariance": var_m},
        )

    cov_im = float(np.cov(excess_i, excess_m, ddof=1)[0, 1])
    beta = cov_im / var_m
    alpha = float(np.mean(excess_i)) - beta * float(np.mean(excess_m))

    var_i = float(np.var(r_i, ddof=1))
    firm_var = var_i - beta * beta * var_m

    if firm_var < 0.0:
        if firm_var < -CLAMP_FIRM_VAR_TOL:
            raise InvalidReturnWindowError(
                "firm-specific variance strongly negative; input data is pathological",
                {"firmSpecificVar": firm_var, "tolerance": CLAMP_FIRM_VAR_TOL},
            )
        if warnings is not None:
            warnings.append(
                f"firm_specific_var had minor negative drift ({firm_var:.3e}); clamped to 0"
            )
        firm_var = 0.0

    return SingleIndexFit(
        alpha_per_period=alpha,
        beta=beta,
        firm_specific_var_per_period=firm_var,
        n_observations=n,
    )


__all__ = ["CLAMP_FIRM_VAR_TOL", "SingleIndexFit", "single_index_metrics"]
