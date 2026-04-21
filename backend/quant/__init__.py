"""Portfolio Manager — Phase 1A Quant Engine.

Pure math only. No I/O, no network, no logging. Data-layer and API concerns
live in sibling packages owned by other agents; see ``docs/SPEC.md`` §9.

The public surface is:

- Types: :class:`StockMetrics`, :class:`MarketMetrics`, :class:`CovarianceMatrix`,
  :class:`RiskProfile`, :class:`ORP`, :class:`CompletePortfolio`,
  :class:`FrontierPoint`, :class:`CALPoint`, :class:`OptimizationResult`,
  :class:`ReturnFrequency`.
- Errors: :class:`QuantError` hierarchy and :class:`ErrorCode`.
- Linear algebra: :func:`build_covariance`, :func:`nearest_psd`,
  :func:`is_symmetric`, :func:`is_psd`, :func:`ensure_psd_covariance`.
- Returns: :func:`expected_returns`, :func:`std_devs`, :func:`sample_covariance`,
  :func:`annualize_mean`, :func:`annualize_std`, :func:`annualize_variance`.
- Sharpe: :func:`sharpe_ratio`.
- CAPM: :func:`capm_required_return`, :func:`capm_total_expected_return`,
  :func:`capm_systematic_variance`, :func:`capm_total_variance`,
  :func:`capm_total_std_dev`.
- Single-Index Model: :func:`single_index_metrics`.
- Optimization: :func:`optimize_markowitz`, :func:`minimum_variance_portfolio`.
- Allocation: :func:`utility_max_allocation`.
- Frontier: :func:`efficient_frontier_points`, :func:`cal_points`.
"""

from __future__ import annotations

from .allocation import utility_max_allocation
from .capm import (
    capm_required_return,
    capm_systematic_variance,
    capm_total_expected_return,
    capm_total_std_dev,
    capm_total_variance,
)
from .errors import (
    ErrorCode,
    InsufficientHistoryError,
    InternalError,
    InvalidReturnWindowError,
    InvalidRiskProfileError,
    OptimizerInfeasibleError,
    OptimizerNonPSDCovarianceError,
    QuantError,
)
from .frontier import cal_points, efficient_frontier_points
from .linalg import (
    PROJECTION_FLOOR,
    PSD_TOL,
    SYMMETRY_TOL,
    build_covariance,
    ensure_psd_covariance,
    is_psd,
    is_symmetric,
    nearest_psd,
)
from .markowitz import optimize_markowitz
from .minvar import minimum_variance_portfolio
from .returns import (
    ANNUALIZATION_FACTORS,
    annualization_factor,
    annualize_mean,
    annualize_std,
    annualize_variance,
    expected_returns,
    sample_covariance,
    std_devs,
)
from .sharpe import sharpe_ratio
from .sim import SingleIndexFit, single_index_metrics
from .types import (
    ORP,
    CALPoint,
    CompletePortfolio,
    CovarianceMatrix,
    FrontierPoint,
    MarketMetrics,
    OptimizationResult,
    ReturnFrequency,
    RiskProfile,
    StockMetrics,
    Ticker,
)

__version__ = "0.1.0"

__all__ = [
    "ANNUALIZATION_FACTORS",
    "ORP",
    "PROJECTION_FLOOR",
    "PSD_TOL",
    "SYMMETRY_TOL",
    "CALPoint",
    "CompletePortfolio",
    "CovarianceMatrix",
    "ErrorCode",
    "FrontierPoint",
    "InsufficientHistoryError",
    "InternalError",
    "InvalidReturnWindowError",
    "InvalidRiskProfileError",
    "MarketMetrics",
    "OptimizationResult",
    "OptimizerInfeasibleError",
    "OptimizerNonPSDCovarianceError",
    "QuantError",
    "ReturnFrequency",
    "RiskProfile",
    "SingleIndexFit",
    "StockMetrics",
    "Ticker",
    "__version__",
    "annualization_factor",
    "annualize_mean",
    "annualize_std",
    "annualize_variance",
    "build_covariance",
    "cal_points",
    "capm_required_return",
    "capm_systematic_variance",
    "capm_total_expected_return",
    "capm_total_std_dev",
    "capm_total_variance",
    "efficient_frontier_points",
    "ensure_psd_covariance",
    "expected_returns",
    "is_psd",
    "is_symmetric",
    "minimum_variance_portfolio",
    "nearest_psd",
    "optimize_markowitz",
    "sample_covariance",
    "sharpe_ratio",
    "single_index_metrics",
    "std_devs",
    "utility_max_allocation",
]
