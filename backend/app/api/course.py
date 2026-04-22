"""Course analytics: ``/api/analytics/performance`` and ``/api/valuation``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_service
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
    rfr = await data_service.get_risk_free_rate()
    svc = ValuationService()
    result, src = await svc.run(
        body,
        data_service=data_service,
        risk_free_rate=rfr.rate,
    )
    response.headers["X-Data-Source"] = _prov(src)
    return result


__all__ = ["router"]
