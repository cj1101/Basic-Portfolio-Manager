"""``POST /api/analytics/performance`` — Treynor, Jensen, SIM, holding windows, FF3."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.data.fama_french_factors import (
    FamaFrenchMonth,
    by_year_month_index,
    load_fama_french_monthly,
)
from app.data.service import DataService, HistoricalResult
from app.errors import InsufficientHistoryError, InvalidReturnWindowError
from app.schemas import (
    AnalyticsPerformanceRequest,
    AnalyticsPerformanceResult,
    CompletePerformanceMetrics,
    FamaFrenchThreePerTicker,
    HoldingPeriodMonthlyReturns,
    MarketMetrics,
    ORPPerformanceMetrics,
    ReturnFrequency,
)
from app.services.optimize_service import MARKET_PROXY_TICKER, MIN_ALIGNED_OBSERVATIONS
from app.services.returns_frame import build_return_frame
from quant import (
    annualization_factor,
    annualize_alpha_monthly,
    capm_expected_return_annualized,
    capm_systematic_variance,
    ensure_psd_covariance,
    expected_return_from_monthly_sample_means,
    fama_french_capm_regression_mkt,
    fama_french_three_regression,
    single_index_metrics,
)
from quant.holding_period_monthly import (
    mean_monthly_arithmetic_geometric,
    simple_monthly_returns_from_close_series,
)
from quant.portfolio_risk import (
    sim_portfolio_variance_decomposition,
    total_variance_from_covariance,
)
from quant.treynor import treynor_ratio

MARKET = MARKET_PROXY_TICKER
SIM_MISMATCH_WARN = 1e-4
_FF_CACHE: dict[int, FamaFrenchMonth] | None = None


def _ff() -> dict[int, FamaFrenchMonth]:
    global _FF_CACHE
    if _FF_CACHE is None:
        _FF_CACHE = by_year_month_index(load_fama_french_monthly())
    return _FF_CACHE


def _ym_from_ts(ts: pd.Timestamp) -> int:
    return int(ts.year) * 100 + int(ts.month)


def _monthly_closes(bars) -> pd.Series:
    s = pd.Series(
        {b.date: float(b.close) for b in bars},
        dtype="float64",
    )
    s.index = pd.to_datetime(s.index)
    return s.sort_index().resample("ME").last().dropna()


def _holding_from_first_ticker_bars(
    bars: list,
) -> list[HoldingPeriodMonthlyReturns]:
    s0 = _monthly_closes(bars)
    out: list[HoldingPeriodMonthlyReturns] = []
    for years, need_months in ((3, 36), (5, 60), (10, 120)):
        if s0.shape[0] < need_months + 1:
            continue
        tail = s0.iloc[-(need_months + 1) :]
        arr = tail.to_numpy(dtype=np.float64)
        rets = simple_monthly_returns_from_close_series(arr)
        ar, geo = mean_monthly_arithmetic_geometric(rets)
        d0 = tail.index[0]
        d1 = tail.index[-1]
        out.append(
            HoldingPeriodMonthlyReturns(
                years=years,
                n_observations=int(rets.size),
                window_start=d0.to_pydatetime().date() if isinstance(d0, pd.Timestamp) else d0,
                window_end=d1.to_pydatetime().date() if isinstance(d1, pd.Timestamp) else d1,
                arithmetic_mean_monthly_return=ar,
                geometric_mean_monthly_return=geo,
            )
        )
    return out


def _ff3_per_ticker(
    bars_by: dict[str, list],
) -> list[FamaFrenchThreePerTicker]:
    fac = _ff()
    res: list[FamaFrenchThreePerTicker] = []
    for t, bars in bars_by.items():
        s = _monthly_closes(bars)
        if s.shape[0] < 5:
            continue
        mkt: list[float] = []
        smb: list[float] = []
        hml: list[float] = []
        rf: list[float] = []
        yx: list[float] = []
        mktc: list[float] = []
        for i in range(1, s.shape[0]):
            ts = s.index[i]
            ym = _ym_from_ts(ts)
            frow = fac.get(ym)
            if frow is None:
                continue
            p0, p1 = float(s.iloc[i - 1]), float(s.iloc[i])
            r = p1 / p0 - 1.0
            mkt.append(frow.mkt_rf)
            smb.append(frow.smb)
            hml.append(frow.hml)
            rf.append(frow.rf)
            yx.append(r - frow.rf)
            mktc.append(frow.mkt_rf)
        if len(yx) < 4:
            continue
        a = np.array(yx, dtype=np.float64)
        a3, b1, b2, b3, n3 = fama_french_three_regression(
            a, np.array(mkt, dtype=np.float64), np.array(smb, dtype=np.float64), np.array(hml, dtype=np.float64)
        )
        _ac, bc, _n2 = fama_french_capm_regression_mkt(
            a, np.array(mktc, dtype=np.float64)
        )
        m_rf = float(np.mean(np.array(rf, dtype=np.float64)))
        mm = float(np.mean(np.array(mkt, dtype=np.float64)))
        ms = float(np.mean(np.array(smb, dtype=np.float64)))
        mh = float(np.mean(np.array(hml, dtype=np.float64)))
        eff = expected_return_from_monthly_sample_means(m_rf, mm, ms, mh, b1, b2, b3)
        ec = capm_expected_return_annualized(m_rf, mm, bc)
        res.append(
            FamaFrenchThreePerTicker(
                ticker=t,
                beta_mkt=b1,
                beta_smb=b2,
                beta_hml=b3,
                alpha=annualize_alpha_monthly(a3),
                n_observations=n3,
                expected_return_ff3=eff,
                expected_return_capm=ec,
            )
        )
    return res


class AnalyticsService:
    async def run(
        self,
        request: AnalyticsPerformanceRequest,
        *,
        data_service: DataService,
    ) -> tuple[AnalyticsPerformanceResult, str]:
        tickers = [str(t).upper().strip() for t in request.tickers]
        if MARKET in tickers:
            raise InvalidReturnWindowError(
                f"{MARKET} is the market proxy and cannot appear in tickers"
            )
        w = np.array([float(request.orp_weights.get(t, 0.0)) for t in tickers], dtype=np.float64)
        s = float(w.sum())
        if abs(s - 1.0) > 1e-4:
            raise InvalidReturnWindowError("orpWeights must sum to 1.0", {"sum": s})

        rfr = await data_service.get_risk_free_rate()
        fetch = [*tickers, MARKET]
        hist: dict[str, HistoricalResult] = {}
        for t in fetch:
            hist[t] = await data_service.get_historical(
                t, frequency=request.return_frequency, lookback_years=request.lookback_years
            )
        # Longer window for 3/5/10y *monthly* mean returns (first ticker; prices only).
        hold_hist = await data_service.get_historical(
            tickers[0], frequency=ReturnFrequency.DAILY, lookback_years=max(12, request.lookback_years)
        )

        warnings: list[str] = list(rfr.warnings)
        sources = [hist[t].source for t in fetch]
        data_source = sources[0] if len({*sources}) == 1 else "mixed"

        frame = build_return_frame(
            {t: hist[t].bars for t in fetch},
            column_order=(*tickers, MARKET),
        )
        if frame.shape[0] < MIN_ALIGNED_OBSERVATIONS:
            raise InsufficientHistoryError(
                ",".join(tickers),
                int(frame.shape[0]),
                MIN_ALIGNED_OBSERVATIONS,
            )

        stock_m = frame[list(tickers)].to_numpy(dtype=np.float64)
        mkt = frame[MARKET].to_numpy(dtype=np.float64)
        factor = annualization_factor(request.return_frequency)
        rf = float(rfr.rate) / factor

        mu_annual = stock_m.mean(axis=0) * factor
        cov = np.cov(stock_m, rowvar=False, ddof=1) * factor
        cov = np.atleast_2d(np.asarray(cov, dtype=np.float64))
        cov = 0.5 * (cov + cov.T)
        qw: list[str] = []
        cov = ensure_psd_covariance(cov, warnings=qw)
        warnings += qw

        m_mean = float(mkt.mean()) * factor
        m_std = float(mkt.std(ddof=1)) * math.sqrt(factor)
        m_var = m_std**2
        market = MarketMetrics(expected_return=m_mean, std_dev=m_std, variance=m_var)

        betas: list[float] = []
        fvars: list[float] = []
        for idx in range(len(tickers)):
            fit = single_index_metrics(
                stock_m[:, idx], mkt, risk_free_per_period=rf, warnings=warnings
            )
            betas.append(float(fit.beta))
            fvars.append(float(fit.firm_specific_var_per_period) * factor)
        b_arr = np.asarray(betas, dtype=np.float64)
        f_arr = np.asarray(fvars, dtype=np.float64)
        w_orp = w

        r_p = stock_m @ w_orp
        rej = single_index_metrics(r_p, mkt, risk_free_per_period=rf, warnings=warnings)
        j_orp_annual = float(rej.alpha_per_period) * factor
        n_obs = int(rej.n_observations)
        e_orp = float(np.dot(w_orp, mu_annual))
        beta_p = float(np.dot(w_orp, b_arr))
        t_orp = treynor_ratio(e_orp, float(rfr.rate), beta_p)

        total_var = total_variance_from_covariance(cov, w_orp)
        sysv, unsyv, sim_sum = sim_portfolio_variance_decomposition(
            w_orp, b_arr, m_var, f_arr
        )
        sim_mis = abs(total_var - sim_sum)
        orp_m = ORPPerformanceMetrics(
            treynor=t_orp,
            jensen_alpha=j_orp_annual,
            n_observations=n_obs,
            total_variance=total_var,
            systematic_variance=sysv,
            unsystematic_variance=unsyv,
            sim_variance_mismatch=sim_mis,
        )
        if sim_mis > SIM_MISMATCH_WARN:
            warnings.append(
                f"SIM variance decomposition differs from w'Σw by {sim_mis:.2e} (tolerance {SIM_MISMATCH_WARN})"
            )

        comp_m: CompletePerformanceMetrics | None = None
        if request.y_star is not None and request.weight_risk_free is not None:
            ys = float(request.y_star)
            e_c = ys * e_orp + (1.0 - ys) * float(rfr.rate)
            b_c = ys * beta_p
            t_c = treynor_ratio(e_c, float(rfr.rate), b_c) if abs(b_c) > 1e-12 else 0.0
            j_c = ys * j_orp_annual
            tv_c = (ys**2) * total_var
            s_c = capm_systematic_variance(b_c, m_var) if abs(b_c) > 0 else 0.0
            u_c = (ys**2) * float(np.sum((w_orp**2) * f_arr))
            sm_c = abs(tv_c - (s_c + u_c))
            comp_m = CompletePerformanceMetrics(
                treynor=t_c,
                jensen_alpha=j_c,
                n_observations=n_obs,
                total_variance=tv_c,
                systematic_variance=s_c,
                unsystematic_variance=u_c,
                sim_variance_mismatch=sm_c,
            )

        w_end = frame.index[-1]
        w_st = frame.index[0]
        d_end = w_end.to_pydatetime().date() if isinstance(w_end, pd.Timestamp) else w_end
        d_start = w_st.to_pydatetime().date() if isinstance(w_st, pd.Timestamp) else w_st
        as_of = datetime.now(UTC)

        holding = _holding_from_first_ticker_bars(hold_hist.bars)
        fama = _ff3_per_ticker({t: hist[t].bars for t in tickers})

        return (
            AnalyticsPerformanceResult(
                as_of=as_of,
                window_start=d_start,
                window_end=d_end,
                risk_free_rate=float(rfr.rate),
                data_source=data_source,
                orp=orp_m,
                complete=comp_m,
                holding=holding,
                fama_french=fama,
                market=market,
                warnings=warnings,
            ),
            data_source,
        )


__all__ = [
    "MARKET",
    "AnalyticsService",
]
