"""Portfolio Manager — Phase 1A Quant Engine.

Pure math only. No I/O, no network, no logging. Data-layer and API concerns
live in sibling packages owned by other agents; see ``docs/SPEC.md`` §9.

The public surface is:

- Types: :class:`StockMetrics`, :class:`MarketMetrics`, :class:`CovarianceMatrix`,
  :class:`CorrelationMatrix`,
  :class:`RiskProfile`, :class:`ORP`, :class:`CompletePortfolio`,
  :class:`FrontierPoint`, :class:`CALPoint`, :class:`OptimizationResult`,
  :class:`ReturnFrequency`.
- Errors: :class:`QuantError` hierarchy and :class:`ErrorCode`.
- Linear algebra: :func:`build_covariance`, :func:`covariance_to_correlation`,
  :func:`nearest_psd`, :func:`is_symmetric`, :func:`is_psd`,
  :func:`ensure_psd_covariance`.
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
from .fama_french_3 import (
    annualize_alpha_monthly,
    capm_expected_return_annualized,
    expected_return_from_monthly_sample_means,
    fama_french_capm_regression_mkt,
    fama_french_three_regression,
)
from .frontier import cal_points, efficient_frontier_points
from .holding_period_monthly import (
    mean_monthly_arithmetic_geometric,
    simple_monthly_returns_from_close_series,
)
from .linalg import (
    PROJECTION_FLOOR,
    PSD_TOL,
    SYMMETRY_TOL,
    build_covariance,
    covariance_to_correlation,
    ensure_psd_covariance,
    is_psd,
    is_symmetric,
    nearest_psd,
)
from .markowitz import optimize_markowitz
from .minvar import minimum_variance_portfolio
from .portfolio_risk import (
    portfolio_beta,
    sim_portfolio_variance_decomposition,
    total_variance_from_covariance,
)
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
from .treynor import treynor_ratio
from .types import (
    ORP,
    CALPoint,
    CompletePortfolio,
    CorrelationMatrix,
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
    "CorrelationMatrix",
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
    "annualize_alpha_monthly",
    "annualize_mean",
    "annualize_std",
    "annualize_variance",
    "build_covariance",
    "cal_points",
    "capm_expected_return_annualized",
    "capm_required_return",
    "capm_systematic_variance",
    "capm_total_expected_return",
    "capm_total_std_dev",
    "capm_total_variance",
    "covariance_to_correlation",
    "efficient_frontier_points",
    "ensure_psd_covariance",
    "expected_return_from_monthly_sample_means",
    "expected_returns",
    "fama_french_capm_regression_mkt",
    "fama_french_three_regression",
    "is_psd",
    "is_symmetric",
    "mean_monthly_arithmetic_geometric",
    "minimum_variance_portfolio",
    "nearest_psd",
    "optimize_markowitz",
    "portfolio_beta",
    "sample_covariance",
    "sharpe_ratio",
    "sim_portfolio_variance_decomposition",
    "simple_monthly_returns_from_close_series",
    "single_index_metrics",
    "std_devs",
    "total_variance_from_covariance",
    "treynor_ratio",
    "utility_max_allocation",
]
