"""Course analytics: ``/api/analytics/performance`` and ``/api/valuation``."""

from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_service
from app.data.calendar import last_trading_day_on_or_before
from app.data.service import DataService
from app.schemas import (
    AnalyticsPerformanceRequest,
    AnalyticsPerformanceResult,
    ValuationRequest,
    ValuationResult,
)
from app.services.analytics_service import AnalyticsService
from app.services.valuation_service import ValuationService

router = APIRouter(tags=["course"])


def _prov(src: str) -> str:
    return (src or "unknown").replace("-", "_").upper()


@router.post(
    "/analytics/performance",
    response_model=AnalyticsPerformanceResult,
    response_model_by_alias=True,
)
async def post_analytics_performance(
    body: AnalyticsPerformanceRequest,
    response: Response,
    data_service: DataService = Depends(get_service),
) -> AnalyticsPerformanceResult:
    svc = AnalyticsService()
    result, src = await svc.run(body, data_service=data_service)
    response.headers["X-Data-Source"] = _prov(src)
    return result


@router.post(
    "/valuation",
    response_model=ValuationResult,
    response_model_by_alias=True,
)
async def post_valuation(
    body: ValuationRequest,
    response: Response,
    data_service: DataService = Depends(get_service),
) -> ValuationResult:
    window_end_rfr: Date | None = (
        last_trading_day_on_or_before(body.as_of) if body.as_of is not None else None
    )
    rfr = await data_service.get_risk_free_rate(window_end=window_end_rfr)
    svc = ValuationService()
    result, src = await svc.run(
        body,
        data_service=data_service,
        risk_free_rate=rfr.rate,
    )
    response.headers["X-Data-Source"] = _prov(src)
    return result


__all__ = ["router"]
