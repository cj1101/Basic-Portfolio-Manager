"""``POST /api/optimize`` — full pipeline end-to-end.

Agent D glue: data layer (Agent B) → quant engine (Agent A) → wire response.
Errors raised anywhere in the stack are either already ``AppError`` subclasses
(from the data layer) or are translated from ``quant`` exceptions inside
:class:`app.services.optimize_service.OptimizeService`. The route stays
thin — no math, no provider access — so every behaviour gets exercised at
the ``OptimizeService`` unit level.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_service
from app.data.service import DataService
from app.schemas import OptimizationRequest, OptimizationResult
from app.services import OptimizeService

# Prefix-less router — mounted under ``/api`` by ``app.api.routes``.
router = APIRouter()


@router.post(
    "/optimize",
    response_model=OptimizationResult,
    response_model_by_alias=True,
)
async def post_optimize(
    body: OptimizationRequest,
    response: Response,
    service: DataService = Depends(get_service),
) -> OptimizationResult:
    optimize_service = OptimizeService()
    svc_result = await optimize_service.run(body, data_service=service)
    _set_provenance(
        response,
        svc_result.provenance.source,
        svc_result.result.warnings,
    )
    return svc_result.result


def _set_provenance(response: Response, source: str, warnings: list[str]) -> None:
    response.headers["X-Data-Source"] = source
    if warnings:
        response.headers["X-Data-Warnings"] = "; ".join(warnings)


__all__ = ["router"]
