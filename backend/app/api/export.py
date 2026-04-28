from __future__ import annotations
import io
import logging
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from datetime import datetime, UTC
from datetime import date as Date

import pandas as pd

from app.api.deps import get_service
from app.data.calendar import last_trading_day_on_or_before
from app.data.service import DataService
from app.schemas import (
    ExportRequest, 
    OptimizationRequest, 
    AnalyticsPerformanceRequest, 
    ValuationRequest, 
    ReturnFrequency
)
from app.services import OptimizeService
from app.services.analytics_service import AnalyticsService
from app.services.valuation_service import ValuationService
from app.services.export_service import ExportService
from app.services.returns_frame import build_return_frame
from app.services.optimize_service import MARKET_PROXY_TICKER
from app.data.fama_french_factors import load_fama_french_monthly, by_year_month_index
from quant.returns import annualization_factor

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/export")
async def post_export(
    body: ExportRequest,
    data_service: DataService = Depends(get_service),
):
    """
    Export all analytical results to an Excel file with formulas.
    This endpoint re-runs all services to ensure a consistent state.
    """
    logger.info("Starting Excel export for tickers: %s", body.tickers)

    window_end_rfr: Date | None = (
        last_trading_day_on_or_before(body.as_of) if body.as_of is not None else None
    )

    # 1. Run Optimize (to get ORP weights and Complete Portfolio parameters)
    optimize_req = OptimizationRequest(
        tickers=body.tickers,
        risk_profile=body.risk_profile,
        return_frequency=body.return_frequency,
        lookback_years=body.lookback_years,
        allow_short=body.allow_short,
        allow_leverage=body.allow_leverage,
        as_of=body.as_of,
    )
    opt_svc = OptimizeService()
    opt_res_container = await opt_svc.run(optimize_req, data_service=data_service)
    opt_res = opt_res_container.result

    anchor: Date | None = body.as_of
    tickers_norm = [str(t).upper().strip() for t in body.tickers]
    fetch = [*tickers_norm, MARKET_PROXY_TICKER]
    hist: dict[str, object] = {}
    for t in fetch:
        hist[t] = await data_service.get_historical(
            t,
            frequency=body.return_frequency,
            lookback_years=body.lookback_years,
            as_of=anchor,
        )
    aligned_log_returns = build_return_frame(
        {t: hist[t].bars for t in fetch},  # type: ignore[attr-defined]
        column_order=tuple([*tickers_norm, MARKET_PROXY_TICKER]),
    )
    ann_k = annualization_factor(body.return_frequency)

    # Monthly closes for FF3 workbook block (simple returns; factors aligned by ym).
    monthly_by: dict[str, pd.Series] = {}
    for t in tickers_norm:
        mb = await data_service.get_historical(
            t,
            frequency=ReturnFrequency.MONTHLY,
            lookback_years=body.lookback_years,
            as_of=anchor,
        )
        s = pd.Series(
            {bar.date: float(bar.close) for bar in mb.bars},
            dtype="float64",
        )
        s.index = pd.to_datetime(s.index)
        monthly_by[t] = s.sort_index().resample("ME").last().dropna()
    joint_px = pd.concat(monthly_by, axis=1, join="inner")
    joint_px = joint_px[tickers_norm].dropna()
    simple_monthly = joint_px.pct_change().dropna()
    fac_idx = by_year_month_index(load_fama_french_monthly())
    anchor_ym_cap2: int | None = None
    if anchor is not None:
        we2 = last_trading_day_on_or_before(anchor)
        anchor_ym_cap2 = we2.year * 100 + we2.month

    rows_ts: list[pd.Timestamp] = []
    fac_rows: list = []
    for ts in simple_monthly.index:
        ym = int(ts.year) * 100 + int(ts.month)
        if anchor_ym_cap2 is not None and ym > anchor_ym_cap2:
            continue
        frow = fac_idx.get(ym)
        if frow is None:
            continue
        rows_ts.append(ts)
        fac_rows.append(frow)

    ff_monthly = pd.DataFrame()
    if rows_ts:
        idx = pd.DatetimeIndex(rows_ts)
        rets_slice = simple_monthly.loc[idx]
        ff_monthly = pd.DataFrame(
            {
                "RF": [f.rf for f in fac_rows],
                "Mkt_RF": [f.mkt_rf for f in fac_rows],
                "SMB": [f.smb for f in fac_rows],
                "HML": [f.hml for f in fac_rows],
            },
            index=idx,
        )
        for t in tickers_norm:
            ff_monthly[t] = rets_slice[t].to_numpy(dtype=float)
    # 2. Run Analytics (performance metrics, FF3, holding periods)
    ana_req = AnalyticsPerformanceRequest(
        tickers=body.tickers,
        orp_weights=opt_res.orp.weights,
        return_frequency=body.return_frequency,
        lookback_years=body.lookback_years,
        y_star=opt_res.complete.y_star,
        weight_risk_free=opt_res.complete.weight_risk_free,
        as_of=body.as_of,
    )
    ana_svc = AnalyticsService()
    ana_res, _ = await ana_svc.run(ana_req, data_service=data_service)
    
    # 3. Run Valuation (DCF, Multiples)
    val_req = ValuationRequest(
        tickers=body.tickers,
        as_of=body.as_of,
        wacc=body.wacc,
        fcff_growth=body.fcff_growth,
        fcff_terminal_growth=body.fcff_terminal_growth,
        cost_of_equity_override=body.cost_of_equity_override,
        ddm_gordon_g=body.ddm_gordon_g,
        ddm_two_stage=body.ddm_two_stage,
    )
    val_svc = ValuationService()
    rfr_latest = await data_service.get_risk_free_rate(window_end=window_end_rfr)
    val_res, _ = await val_svc.run(val_req, data_service=data_service, risk_free_rate=rfr_latest.rate)

    # ^GSPC = S&P 500 price index monthly levels for workbook only (nominal formulas). API analytics still use SPY where coded.
    market_index_hist = await data_service.get_historical(
        "^GSPC",
        frequency=ReturnFrequency.MONTHLY,
        lookback_years=10,
        as_of=body.as_of,
    )
    
    # Use bundled Fama-French factors for the historical RF series
    ff_factors = load_fama_french_monthly()
    anchor_ym_cap: int | None = None
    if body.as_of is not None:
        we = last_trading_day_on_or_before(body.as_of)
        anchor_ym_cap = we.year * 100 + we.month

    rf_series = []
    for f in ff_factors:
        if anchor_ym_cap is not None and f.ym > anchor_ym_cap:
            continue
        year = f.ym // 100
        month = f.ym % 100
        dt_str = f"{year}-{month:02d}-01"
        rf_series.append({"date": dt_str, "rate": f.rf})

    # 5. Build Workbook
    exp_svc = ExportService()
    excel_io = exp_svc.build_workbook(
        optimize=opt_res,
        analytics=ana_res,
        valuation=val_res,
        market_index_bars=market_index_hist.bars,
        rf_series=rf_series,
        risk_profile=body.risk_profile,
        allow_leverage=body.allow_leverage,
        export_request=body,
        aligned_log_returns=aligned_log_returns,
        annualization_factor=ann_k,
        allow_short=body.allow_short,
        ff_monthly=ff_monthly,
    )
    
    filename = f"Portfolio_Analysis_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.xlsx"
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Access-Control-Expose-Headers': 'Content-Disposition'
    }
    
    return StreamingResponse(
        excel_io, 
        headers=headers, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
