"""CAPM required return and variance decomposition.

Formulas (``.cursor/rules/quant.mdc`` §5):

- ``r_CAPM = rᶠ + β · (E(r_M) − rᶠ)``
- ``E(r_i) = r_CAPM + α_i``
- ``σ²_i    = β² · σ²_M + σ²(e_i)``  (systematic + firm-specific variance)

All inputs and outputs are annualized decimals.
"""

from __future__ import annotations

import math


def capm_required_return(
    beta: float,
    market_expected_return: float,
    risk_free_rate: float,
) -> float:
    """``rᶠ + β · (E(r_M) − rᶠ)``. Zero-beta → rᶠ; β=1 → E(r_M)."""
    return float(risk_free_rate) + float(beta) * (
        float(market_expected_return) - float(risk_free_rate)
    )


def capm_total_expected_return(
    beta: float,
    alpha: float,
    market_expected_return: float,
    risk_free_rate: float,
) -> float:
    """``r_CAPM + α``; single-index view of an asset's expected return."""
    return capm_required_return(beta, market_expected_return, risk_free_rate) + float(alpha)


def capm_systematic_variance(beta: float, market_variance: float) -> float:
    """``β² · σ²_M``. The share of an asset's variance explained by the market."""
    if float(market_variance) < 0:
        raise ValueError(f"market_variance must be non-negative; got {market_variance}")
    return float(beta) ** 2 * float(market_variance)


def capm_total_variance(
    beta: float,
    market_variance: float,
    firm_specific_var: float,
) -> float:
    """``β² · σ²_M + σ²(e)``. Total variance under the single-index model."""
    if float(firm_specific_var) < 0:
        raise ValueError(f"firm_specific_var must be non-negative; got {firm_specific_var}")
    return capm_systematic_variance(beta, market_variance) + float(firm_specific_var)


def capm_total_std_dev(
    beta: float,
    market_variance: float,
    firm_specific_var: float,
) -> float:
    return math.sqrt(capm_total_variance(beta, market_variance, firm_specific_var))


__all__ = [
    "capm_required_return",
    "capm_systematic_variance",
    "capm_total_expected_return",
    "capm_total_std_dev",
    "capm_total_variance",
]
