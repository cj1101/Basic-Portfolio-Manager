"""Utility-maximizing allocation between the ORP and the risk-free asset.

Per ``.cursor/rules/quant.mdc`` §4:

- Objective: ``U(y) = y·E(r_ORP) + (1 − y)·rᶠ − 0.5·A·y²·σ²_ORP``
- Closed form: ``y* = (E(r_ORP) − rᶠ) / (A · σ²_ORP)``
- ``y* > 1`` → leverage (``weightRiskFree = 1 − y* < 0``).
- If a ``target_return`` exceeds ``E(r_ORP)``, compute
  ``y_target = (targetReturn − rᶠ) / (E(r_ORP) − rᶠ)`` and use
  ``max(y*, y_target)`` with a warning.
- ``y* < 0`` is **out of scope for v1** — raise ``INVALID_RISK_PROFILE``.
- When ``allow_leverage=False`` and ``y_final > 1``, clamp to 1 with a
  warning.

Returned as :class:`quant.types.CompletePortfolio`.
"""

from __future__ import annotations

import math

from .errors import InvalidRiskProfileError
from .types import ORP, CompletePortfolio, RiskProfile


def utility_max_allocation(
    orp: ORP,
    risk_free_rate: float,
    risk_profile: RiskProfile,
    allow_leverage: bool,
    warnings: list[str] | None = None,
) -> CompletePortfolio:
    """Construct the CAL-point that maximizes the investor's utility."""
    rf = float(risk_free_rate)
    e_orp = float(orp.expected_return)
    var_orp = float(orp.variance)
    sd_orp = float(orp.std_dev)
    a = float(risk_profile.risk_aversion)

    if not (math.isfinite(rf) and math.isfinite(e_orp) and math.isfinite(var_orp)):
        raise InvalidRiskProfileError("non-finite inputs to allocation")
    if var_orp <= 0.0:
        raise InvalidRiskProfileError(
            "ORP variance must be strictly positive",
            {"variance": var_orp},
        )
    if a <= 0.0:
        raise InvalidRiskProfileError("risk_aversion must be strictly positive", {"A": a})

    risk_premium = e_orp - rf
    y_star_optimal = risk_premium / (a * var_orp)

    if y_star_optimal < 0.0:
        raise InvalidRiskProfileError(
            "optimal y* is negative — client would short the ORP; out of scope for v1",
            {"yStar": y_star_optimal, "riskPremium": risk_premium},
        )

    y_final = y_star_optimal

    target_return = risk_profile.target_return
    if target_return is not None:
        tr = float(target_return)
        if tr > e_orp:
            if risk_premium <= 0.0:
                raise InvalidRiskProfileError(
                    "cannot meet target_return: ORP has no risk premium over rᶠ",
                    {"targetReturn": tr, "expectedReturn": e_orp, "riskFree": rf},
                )
            y_target = (tr - rf) / risk_premium
            if y_target > y_star_optimal:
                if warnings is not None:
                    warnings.append(
                        f"targetReturn={tr:.6f} exceeds E(r_ORP)={e_orp:.6f}; "
                        f"overriding y* from {y_star_optimal:.6f} to y_target={y_target:.6f}"
                    )
                y_final = y_target

    if not allow_leverage and y_final > 1.0:
        if warnings is not None:
            warnings.append(f"leverage disabled: clamping y from {y_final:.6f} to 1.000000")
        y_final = 1.0

    leverage_used = y_final > 1.0

    weights = {t: y_final * w for t, w in orp.weights.items()}
    expected_return = rf + y_final * risk_premium
    std_dev = y_final * sd_orp
    weight_risk_free = 1.0 - y_final

    return CompletePortfolio(
        y_star=y_final,
        weight_risk_free=weight_risk_free,
        weights=weights,
        expected_return=expected_return,
        std_dev=std_dev,
        leverage_used=leverage_used,
    )


__all__ = ["utility_max_allocation"]
