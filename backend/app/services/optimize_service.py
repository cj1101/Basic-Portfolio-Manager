"""Orchestrates a full ``/api/optimize`` pipeline.

The service is a thin async coordinator that:

1. Gathers historical bars (for every requested ticker plus the SPY market
   proxy) and the current risk-free rate through the existing
   :class:`app.data.service.DataService` (Agent B).
2. Builds an aligned return matrix on a shared date index.
3. Calls the pure :mod:`quant` functions (Agent A) to compute per-stock
   metrics, the ORP, the utility-max Complete Portfolio, the efficient
   frontier and the Capital Allocation Line.
4. Surfaces provenance + warnings from both layers on the response.

No provider calls or math live here — this module is the integration seam
owned by Agent D.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.data.service import DataService, HistoricalResult
from app.errors import (
    AppError,
    InsufficientHistoryError,
    InvalidReturnWindowError,
    UnknownTickerError,
)
from app.services.returns_frame import build_return_frame
from app.schemas import (
    CorrelationMatrix,
    CovarianceMatrix,
    ErrorCode,
    MarketMetrics,
    OptimizationRequest,
    OptimizationResult,
    ReturnFrequency,
    StockMetrics,
)
from quant import (
    InvalidRiskProfileError as QuantInvalidRiskProfileError,
)
from quant import (
    OptimizerInfeasibleError as QuantOptimizerInfeasibleError,
)
from quant import (
    OptimizerNonPSDCovarianceError as QuantOptimizerNonPSDCovarianceError,
)
from quant import (
    annualization_factor,
    cal_points,
    covariance_to_correlation,
    efficient_frontier_points,
    ensure_psd_covariance,
    optimize_markowitz,
    single_index_metrics,
    utility_max_allocation,
)
from quant.errors import ErrorCode as QuantErrorCode

MARKET_PROXY_TICKER: str = "SPY"
"""Ticker used as the market benchmark for CAPM/SIM regressions."""

MIN_ALIGNED_OBSERVATIONS: int = 30
"""Minimum return observations on the shared date grid after inner-join."""


@dataclass(frozen=True)
class OptimizeProvenance:
    """Where the price data came from. Used to set ``X-Data-Source`` header."""

    source: str
    per_ticker_sources: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OptimizeServiceResult:
    result: OptimizationResult
    provenance: OptimizeProvenance


class OptimizeService:
    """Stateless orchestrator. Instantiate once per request (or module-level)."""

    async def run(
        self,
        request: OptimizationRequest,
        *,
        data_service: DataService,
    ) -> OptimizeServiceResult:
        tickers = _normalize_request_tickers(request.tickers)

        # Fetch risk-free rate and all historical series concurrently. The
        # market proxy is fetched alongside the user's universe so CAPM/SIM
        # regressions use the exact same window of bars.
        fetch_tickers = [*tickers, MARKET_PROXY_TICKER]

        rfr_task = asyncio.create_task(data_service.get_risk_free_rate())
        hist_tasks = {
            t: asyncio.create_task(
                data_service.get_historical(
                    t,
                    frequency=request.return_frequency,
                    lookback_years=request.lookback_years,
                )
            )
            for t in fetch_tickers
        }

        try:
            rfr_result = await rfr_task
            hist_results: dict[str, HistoricalResult] = {
                t: await task for t, task in hist_tasks.items()
            }
        except AppError:
            # AppError subclasses (UnknownTickerError, RateLimitError,
            # ProviderUnavailableError, ...) already carry the taxonomy code
            # and map 1:1 to the HTTP envelope via app.errors.app_error_handler.
            raise

        warnings: list[str] = list(rfr_result.warnings)
        per_ticker_sources: dict[str, str] = {}
        for t, res in hist_results.items():
            per_ticker_sources[t] = res.source
            for warning in res.warnings:
                warnings.append(f"{t}: {warning}")

        # ------------------------------------------------------------------
        # Assemble the aligned per-period return matrix.
        # ------------------------------------------------------------------
        frame = build_return_frame(
            {t: res.bars for t, res in hist_results.items()},
            column_order=(*tickers, MARKET_PROXY_TICKER),
        )

        if frame.shape[0] < MIN_ALIGNED_OBSERVATIONS:
            raise InsufficientHistoryError(
                ", ".join(tickers),
                int(frame.shape[0]),
                MIN_ALIGNED_OBSERVATIONS,
            )

        frequency: ReturnFrequency = request.return_frequency
        factor = annualization_factor(frequency)

        stock_frame = frame[list(tickers)]
        market_series = frame[MARKET_PROXY_TICKER]

        # Per-period moments (used for the SIM regression below). The quant
        # engine's ``expected_returns``/``sample_covariance`` annualize for us;
        # we compute the per-period versions manually from the same arrays so
        # the regression coefficients land in consistent units.
        stock_returns = stock_frame.to_numpy(dtype=np.float64)
        market_returns = market_series.to_numpy(dtype=np.float64)

        mu_annual = stock_returns.mean(axis=0) * factor
        sd_annual = stock_returns.std(axis=0, ddof=1) * math.sqrt(factor)
        cov_annual = np.cov(stock_returns, rowvar=False, ddof=1) * factor
        cov_annual = np.atleast_2d(np.asarray(cov_annual, dtype=np.float64))
        cov_annual = 0.5 * (cov_annual + cov_annual.T)

        quant_warnings: list[str] = []

        try:
            cov_psd = ensure_psd_covariance(cov_annual, warnings=quant_warnings)
        except QuantOptimizerNonPSDCovarianceError as exc:
            raise AppError(
                _quant_code_to_app_code(exc.code),
                exc.message,
                exc.details,
            ) from exc

        # Market moments — annualized — power the MarketMetrics block.
        market_mean = float(market_returns.mean()) * factor
        market_std = float(market_returns.std(ddof=1)) * math.sqrt(factor)
        market_variance = float(market_std) ** 2

        # Per-stock CAPM/SIM fit (alpha, beta, firm-specific variance).
        stock_metrics: list[StockMetrics] = []
        for idx, ticker in enumerate(tickers):
            fit = single_index_metrics(
                stock_returns[:, idx],
                market_returns,
                risk_free_per_period=float(rfr_result.rate) / factor,
                warnings=quant_warnings,
            )
            # Annualize alpha and firm-specific variance; beta is
            # frequency-invariant (SPEC §5 / quant.mdc §5).
            stock_metrics.append(
                StockMetrics(
                    ticker=ticker,
                    expected_return=float(mu_annual[idx]),
                    std_dev=float(sd_annual[idx]),
                    beta=float(fit.beta),
                    alpha=float(fit.alpha_per_period) * factor,
                    firm_specific_var=float(fit.firm_specific_var_per_period) * factor,
                    n_observations=int(fit.n_observations),
                )
            )

        # ------------------------------------------------------------------
        # ORP, Complete Portfolio, Frontier, CAL.
        # ------------------------------------------------------------------
        try:
            orp = optimize_markowitz(
                list(tickers),
                mu_annual,
                cov_psd,
                risk_free_rate=float(rfr_result.rate),
                allow_short=request.allow_short,
                allow_leverage=request.allow_leverage,
                warnings=quant_warnings,
            )
            complete = utility_max_allocation(
                orp,
                float(rfr_result.rate),
                request.risk_profile,
                allow_leverage=request.allow_leverage,
                warnings=quant_warnings,
            )
            frontier = efficient_frontier_points(
                mu_annual,
                cov_psd,
                frontier_resolution=request.frontier_resolution,
                warnings=quant_warnings,
            )
            cal = cal_points(orp, float(rfr_result.rate), y_star=complete.y_star)
        except QuantOptimizerInfeasibleError as exc:
            raise AppError(
                _quant_code_to_app_code(exc.code),
                exc.message,
                exc.details,
            ) from exc
        except QuantInvalidRiskProfileError as exc:
            raise AppError(
                _quant_code_to_app_code(exc.code),
                exc.message,
                exc.details,
            ) from exc
        except QuantOptimizerNonPSDCovarianceError as exc:
            raise AppError(
                _quant_code_to_app_code(exc.code),
                exc.message,
                exc.details,
            ) from exc

        # Every weight dict must include every requested ticker, even at 0
        # (CONTRACTS §6 rule 4). The unconstrained tangency already does this
        # but we make it explicit for the long-only path which may drop
        # near-zeros.
        orp_weights = {t: float(orp.weights.get(t, 0.0)) for t in tickers}
        complete_weights = {t: float(complete.weights.get(t, 0.0)) for t in tickers}

        orp.weights = orp_weights
        complete.weights = complete_weights

        market = MarketMetrics(
            expected_return=market_mean,
            std_dev=market_std,
            variance=market_variance,
        )

        covariance = CovarianceMatrix(
            tickers=list(tickers),
            matrix=[
                [float(cov_psd[i, j]) for j in range(len(tickers))] for i in range(len(tickers))
            ],
        )
        rho = covariance_to_correlation(cov_psd)
        n_t = len(tickers)
        correlation = CorrelationMatrix(
            tickers=list(tickers),
            matrix=[[float(rho[i, j]) for j in range(n_t)] for i in range(n_t)],
        )

        as_of = _as_of_from_frame(frame)

        result = OptimizationResult(
            request_id=f"opt_{uuid.uuid4().hex[:12]}",
            as_of=as_of,
            risk_free_rate=float(rfr_result.rate),
            market=market,
            stocks=stock_metrics,
            covariance=covariance,
            correlation=correlation,
            orp=orp,
            complete=complete,
            frontier_points=frontier,
            cal_points=cal,
            warnings=warnings + quant_warnings,
        )

        provenance = OptimizeProvenance(
            source=_aggregate_source(per_ticker_sources),
            per_ticker_sources=per_ticker_sources,
        )

        return OptimizeServiceResult(result=result, provenance=provenance)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_request_tickers(raw: list[str]) -> tuple[str, ...]:
    """Validate, uppercase, dedupe tickers while preserving input order.

    Reject the SPY proxy appearing in the user universe — it is forced in
    automatically as the market benchmark and including it twice would double
    its weight in the CAPM regression.
    """
    seen: list[str] = []
    for raw_t in raw:
        t = (raw_t or "").strip().upper()
        if not t:
            raise InvalidReturnWindowError("ticker must be non-empty")
        if t == MARKET_PROXY_TICKER:
            raise InvalidReturnWindowError(
                f"{MARKET_PROXY_TICKER} is used as the market proxy and cannot "
                "also appear as a portfolio holding",
                {"ticker": t},
            )
        if t in seen:
            continue
        seen.append(t)
    if len(seen) < 2:
        raise InvalidReturnWindowError(
            "at least 2 distinct tickers are required", {"tickers": seen}
        )
    return tuple(seen)


def _as_of_from_frame(frame: pd.DataFrame) -> datetime:
    if frame.empty:
        return datetime.now(UTC)
    last = frame.index[-1]
    if isinstance(last, pd.Timestamp):
        dt = last.to_pydatetime()
    else:  # pragma: no cover - pandas always returns Timestamp
        dt = datetime.fromisoformat(str(last))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _aggregate_source(sources: dict[str, str]) -> str:
    values = {src for src in sources.values() if src}
    if not values:
        return "unknown"
    if len(values) == 1:
        return next(iter(values))
    return "mixed"


_QUANT_TO_APP_CODE: dict[QuantErrorCode, ErrorCode] = {
    member: ErrorCode(member.value) for member in QuantErrorCode
}


def _quant_code_to_app_code(code: QuantErrorCode) -> ErrorCode:
    """Translate a ``quant.errors.ErrorCode`` into ``app.schemas.ErrorCode``."""
    return _QUANT_TO_APP_CODE[code]


__all__ = [
    "MARKET_PROXY_TICKER",
    "MIN_ALIGNED_OBSERVATIONS",
    "OptimizeProvenance",
    "OptimizeService",
    "OptimizeServiceResult",
]
