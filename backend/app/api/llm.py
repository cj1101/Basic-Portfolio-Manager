"""LLM provider metadata endpoints.

These routes exist so the frontend Settings panel can populate a model
selector without ever seeing the OpenRouter API key. The server proxies
``GET https://openrouter.ai/api/v1/models``, trims the payload to the
handful of fields the UI needs, and caches the result in-process for
``llm_models_cache_ttl_seconds`` (default 5 min).

When ``OPENROUTER_API_KEY`` is unset the proxy still works (OpenRouter's
``/models`` endpoint is public) but ``llmAvailable`` on ``/api/llm/default``
is set to ``false`` so the UI can grey out the LLM toggle.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.api.deps import get_chat_service, get_settings_dep
from app.errors import AppError
from app.schemas import ErrorCode
from app.services.chat.service import ChatService
from app.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])


class _CamelOut(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ModelPricing(_CamelOut):
    prompt: str | None = None
    completion: str | None = None


class LLMModel(_CamelOut):
    id: str
    name: str
    context_length: int | None = Field(default=None)
    pricing: ModelPricing | None = None


class LLMModelsResponse(_CamelOut):
    models: list[LLMModel]
    cached: bool
    fetched_at: float


class LLMDefaultResponse(_CamelOut):
    llm_available: bool
    default_model: str
    base_url: str


_cache_lock = asyncio.Lock()
_cache: dict[str, Any] = {"models": None, "fetched_at": 0.0}


async def _fetch_openrouter_models(base_url: str, api_key: str | None) -> list[LLMModel]:
    url = f"{base_url.rstrip('/')}/models"
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("openrouter: /models fetch failed: %s", exc)
        raise AppError(
            ErrorCode.LLM_UNAVAILABLE,
            "Could not reach the OpenRouter model catalogue.",
            {"reason": "connection"},
        ) from exc

    if resp.status_code >= 400:
        logger.warning("openrouter: /models returned HTTP %s", resp.status_code)
        raise AppError(
            ErrorCode.LLM_UNAVAILABLE,
            f"OpenRouter /models returned HTTP {resp.status_code}.",
            {"reason": "status_error", "status": resp.status_code},
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise AppError(
            ErrorCode.LLM_UNAVAILABLE,
            "OpenRouter /models returned invalid JSON.",
            {"reason": "malformed_response"},
        ) from exc

    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        raise AppError(
            ErrorCode.LLM_UNAVAILABLE,
            "OpenRouter /models returned an unexpected shape.",
            {"reason": "malformed_response"},
        )

    out: list[LLMModel] = []
    for entry in raw_models:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        name = entry.get("name") or model_id
        ctx_len = entry.get("context_length")
        ctx_len_int = int(ctx_len) if isinstance(ctx_len, int | float) else None
        pricing_raw = entry.get("pricing") if isinstance(entry.get("pricing"), dict) else None
        pricing_obj: ModelPricing | None = None
        if pricing_raw is not None:
            pricing_obj = ModelPricing(
                prompt=_coerce_str(pricing_raw.get("prompt")),
                completion=_coerce_str(pricing_raw.get("completion")),
            )
        out.append(
            LLMModel(
                id=model_id,
                name=str(name),
                context_length=ctx_len_int,
                pricing=pricing_obj,
            )
        )
    out.sort(key=lambda m: m.id)
    return out


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


@router.get(
    "/models",
    response_model=LLMModelsResponse,
    response_model_by_alias=True,
)
async def get_llm_models(
    settings: Settings = Depends(get_settings_dep),
) -> LLMModelsResponse:
    now = time.monotonic()
    ttl = max(1, int(settings.llm_models_cache_ttl_seconds))
    async with _cache_lock:
        cached = _cache.get("models")
        fetched_at = float(_cache.get("fetched_at", 0.0) or 0.0)
        if cached is not None and (now - fetched_at) < ttl:
            return LLMModelsResponse(models=cached, cached=True, fetched_at=fetched_at)
        models = await _fetch_openrouter_models(
            settings.openrouter_base_url, settings.openrouter_api_key
        )
        _cache["models"] = models
        _cache["fetched_at"] = now
    return LLMModelsResponse(models=models, cached=False, fetched_at=now)


@router.get(
    "/default",
    response_model=LLMDefaultResponse,
    response_model_by_alias=True,
)
async def get_llm_default(
    settings: Settings = Depends(get_settings_dep),
    chat_service: ChatService = Depends(get_chat_service),
) -> LLMDefaultResponse:
    return LLMDefaultResponse(
        llm_available=chat_service.llm_available,
        default_model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
    )


def reset_models_cache() -> None:
    """Test helper — force the next /api/llm/models call to re-fetch."""

    _cache["models"] = None
    _cache["fetched_at"] = 0.0


__all__ = [
    "LLMDefaultResponse",
    "LLMModel",
    "LLMModelsResponse",
    "ModelPricing",
    "reset_models_cache",
    "router",
]
