"""HTTP routes exposed under ``/api`` (SPEC §5.1–5.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.api.chat import router as chat_router
from app.api.deps import get_service
from app.api.optimize import router as optimize_router
from app.data.service import DataService
from app.schemas import (
    HistoricalResponse,
    Quote,
    ReturnFrequency,
    RiskFreeRateResponse,
    Ticker,
)

router = APIRouter(prefix="/api")


@router.get("/quote", response_model=Quote, response_model_by_alias=True)
async def get_quote(
    response: Response,
    ticker: Ticker = Query(..., description="Uppercase ticker symbol"),
    service: DataService = Depends(get_service),
) -> Quote:
    result = await service.get_quote(ticker)
    _set_provenance(response, result.source, result.warnings)
    return result.quote


@router.get(
    "/historical",
    response_model=HistoricalResponse,
    response_model_by_alias=True,
)
async def get_historical(
    response: Response,
    ticker: Ticker = Query(..., description="Uppercase ticker symbol"),
    frequency: ReturnFrequency = Query(ReturnFrequency.DAILY),
    years: int = Query(5, ge=1, le=20, description="Lookback window in years"),
    service: DataService = Depends(get_service),
) -> HistoricalResponse:
    result = await service.get_historical(
        ticker, frequency=frequency, lookback_years=years
    )
    _set_provenance(response, result.source, result.warnings)
    return HistoricalResponse(
        ticker=result.ticker, frequency=result.frequency, bars=result.bars
    )


@router.get(
    "/risk-free-rate",
    response_model=RiskFreeRateResponse,
    response_model_by_alias=True,
)
async def get_risk_free_rate(
    response: Response,
    service: DataService = Depends(get_service),
) -> RiskFreeRateResponse:
    result = await service.get_risk_free_rate()
    _set_provenance(response, result.source, result.warnings)
    return RiskFreeRateResponse(rate=result.rate, as_of=result.as_of, source=result.source)


def _set_provenance(response: Response, source: str, warnings: list[str]) -> None:
    response.headers["X-Data-Source"] = source
    if warnings:
        response.headers["X-Data-Warnings"] = "; ".join(warnings)


router.include_router(optimize_router)
router.include_router(chat_router)


__all__ = ["router"]
