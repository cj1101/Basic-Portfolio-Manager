from __future__ import annotations
import io
import logging
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from datetime import datetime, UTC

from app.api.deps import get_service
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
from app.data.fama_french_factors import load_fama_french_monthly

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
    
    # 1. Run Optimize (to get ORP weights and Complete Portfolio parameters)
    optimize_req = OptimizationRequest(
        tickers=body.tickers,
        risk_profile=body.risk_profile,
        return_frequency=body.return_frequency,
        lookback_years=body.lookback_years,
        allow_short=body.allow_short,
        allow_leverage=body.allow_leverage
    )
    opt_svc = OptimizeService()
    opt_res_container = await opt_svc.run(optimize_req, data_service=data_service)
    opt_res = opt_res_container.result
    
    # 2. Run Analytics (performance metrics, FF3, holding periods)
    ana_req = AnalyticsPerformanceRequest(
        tickers=body.tickers,
        orp_weights=opt_res.orp.weights,
        return_frequency=body.return_frequency,
        lookback_years=body.lookback_years,
        y_star=opt_res.complete.y_star,
        weight_risk_free=opt_res.complete.weight_risk_free
    )
    ana_svc = AnalyticsService()
    ana_res, _ = await ana_svc.run(ana_req, data_service=data_service)
    
    # 3. Run Valuation (DCF, Multiples)
    val_req = ValuationRequest(
        tickers=body.tickers,
        wacc=body.wacc,
        fcff_growth=body.fcff_growth,
        fcff_terminal_growth=body.fcff_terminal_growth,
        cost_of_equity_override=body.cost_of_equity_override,
        ddm_gordon_g=body.ddm_gordon_g,
        ddm_two_stage=body.ddm_two_stage
    )
    val_svc = ValuationService()
    rfr_latest = await data_service.get_risk_free_rate()
    val_res, _ = await val_svc.run(val_req, data_service=data_service, risk_free_rate=rfr_latest.rate)
    
    # 4. Fetch 10y SPY and RF series for the sheets
    spy_hist = await data_service.get_historical("SPY", frequency=ReturnFrequency.MONTHLY, lookback_years=10)
    
    # Use bundled Fama-French factors for the historical RF series
    ff_factors = load_fama_french_monthly()
    # Map to format expected by ExportService
    rf_series = []
    for f in ff_factors:
        # Convert YM (e.g. 202411) to a date-like string or object
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
        spy_bars=spy_hist.bars,
        rf_series=rf_series
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
