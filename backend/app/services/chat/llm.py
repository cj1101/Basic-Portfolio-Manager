"""Thin async wrapper around OpenRouter's OpenAI-compatible Chat Completions API.

Goals
-----
- Hard timeout (``chat_llm_timeout_seconds``) so we meet the ``< 4 s`` target
  from ``docs/SPEC.md`` §6.
- Every failure mode maps onto :data:`ErrorCode.LLM_UNAVAILABLE` — we never
  leak a raw OpenRouter exception to the client per SPEC §6 "Error taxonomy".
- The user prompt is bounded: at most the last :data:`MAX_HISTORY_TURNS`
  messages, and the portfolio context is serialised with 4 dp rounding so the
  JSON stays small and auditable.
- Model selection is **per-request**: the frontend Settings panel may pass a
  specific OpenRouter slug (e.g. ``anthropic/claude-3.5-sonnet``); if omitted
  we fall back to the ``OPENROUTER_MODEL`` env default.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.errors import AppError
from app.schemas import ChatMessage, OptimizationResult
from app.settings import Settings

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS: int = 10
MAX_OUTPUT_TOKENS: int = 600

# Matches the model-slug shape accepted by OpenRouter: ``vendor/name`` with an
# optional ``:variant`` tag and ``-``/``_``/``.``/digits in the segments. Keep
# this strict so a malicious payload cannot sneak CR/LF into a header value.
MODEL_SLUG_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-._:/]{0,99}$")

_SYSTEM_PROMPT = (
    "You are the Portfolio Manager chat assistant. The user is looking at a "
    "mean-variance optimised portfolio and may ask about Sharpe, alpha, beta, "
    "the Optimal Risky Portfolio (ORP), the Capital Allocation Line (CAL), "
    "leverage (y*), or individual tickers. Use the JSON portfolio snapshot "
    "attached to the most recent user turn as the single source of truth — "
    "never invent numbers. If the snapshot is missing, say so. Keep answers "
    "short (<= 6 sentences), cite the exact numbers you use, and prefer "
    "annualised decimals (e.g. 0.1523) or percentages with two decimals. "
    "Never give personalised investment advice or make promises about "
    "future returns."
)


def validate_model_slug(slug: str) -> str:
    """Return ``slug`` if it is a safe OpenRouter model identifier.

    Raises :class:`AppError` with :data:`ErrorCode.LLM_UNAVAILABLE` otherwise.
    """

    if not MODEL_SLUG_RE.match(slug):
        raise AppError(
            _llm_code(),
            "Invalid model identifier.",
            {"reason": "invalid_model_slug", "value": slug[:120]},
        )
    return slug


class OpenRouterChatClient:
    """Minimal async OpenRouter client for chat completions.

    OpenRouter exposes an OpenAI-compatible REST surface so we can reuse the
    ``openai`` Python SDK as transport — only ``base_url`` and a pair of
    attribution headers change.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 30.0,
        http_referer: str | None = None,
        app_title: str | None = None,
    ) -> None:
        # Defer the import so the module loads even when the `openai` package
        # isn't available in trimmed-down test environments.
        from openai import AsyncOpenAI

        self._default_model = validate_model_slug(model)
        self._timeout = timeout_seconds
        headers: dict[str, str] = {}
        if http_referer:
            headers["HTTP-Referer"] = http_referer
        if app_title:
            headers["X-Title"] = app_title
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            default_headers=headers or None,
        )

    @property
    def model(self) -> str:
        return self._default_model

    async def close(self) -> None:
        await self._client.close()

    async def answer(
        self,
        messages: list[ChatMessage],
        context: OptimizationResult | None,
        *,
        model: str | None = None,
    ) -> tuple[str, str]:
        """Return ``(answer_text, model_used)``."""

        bounded = messages[-MAX_HISTORY_TURNS:]
        if not bounded:
            raise AppError(
                _llm_code(),
                "Cannot call the LLM with an empty message list.",
            )
        last_user = bounded[-1]
        context_blob = _serialize_context(context)
        user_content = (
            f"Portfolio snapshot (JSON):\n{context_blob}\n\nUser question:\n{last_user.content}"
        )

        payload: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for msg in bounded[:-1]:
            payload.append({"role": msg.role, "content": msg.content})
        payload.append({"role": "user", "content": user_content})

        chosen = validate_model_slug(model) if model else self._default_model
        logger.info("openrouter: chat request model=%s msgs=%d", chosen, len(payload))

        try:
            response = await self._client.chat.completions.create(
                model=chosen,
                messages=payload,  # type: ignore[arg-type]
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.2,
            )
        except Exception as exc:
            _raise_llm_unavailable(exc)

        try:
            answer = response.choices[0].message.content or ""
        except (IndexError, AttributeError) as exc:
            logger.warning("openrouter: malformed completion response: %s", exc)
            raise AppError(
                _llm_code(),
                "OpenRouter returned a malformed response.",
                {"reason": "malformed_response"},
            ) from exc
        stripped = answer.strip()
        if not stripped:
            raise AppError(
                _llm_code(),
                "OpenRouter returned an empty answer.",
                {"reason": "empty_response"},
            )
        return stripped, chosen


def build_openrouter_client(settings: Settings) -> OpenRouterChatClient | None:
    if not settings.openrouter_api_key:
        return None
    return OpenRouterChatClient(
        settings.openrouter_api_key,
        model=settings.openrouter_model,
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.chat_llm_timeout_seconds,
        http_referer=settings.openrouter_http_referer,
        app_title=settings.openrouter_app_title,
    )


# Keep the legacy name as an alias so downstream imports keep working until
# every caller migrates. Remove in a follow-up cleanup PR.
build_openai_client = build_openrouter_client


def _serialize_context(context: OptimizationResult | None) -> str:
    if context is None:
        return "null"
    payload: dict[str, Any] = context.model_dump(mode="json", by_alias=True, exclude_none=True)
    return json.dumps(_round_floats(payload, 4), separators=(",", ":"))


def _round_floats(value: Any, ndigits: int) -> Any:
    if isinstance(value, float):
        return round(value, ndigits)
    if isinstance(value, dict):
        return {k: _round_floats(v, ndigits) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_floats(v, ndigits) for v in value]
    return value


def _llm_code():
    # Local import avoids a circular dependency with app.schemas via app.errors.
    from app.schemas import ErrorCode

    return ErrorCode.LLM_UNAVAILABLE


def _raise_llm_unavailable(exc: BaseException) -> None:
    """Map every OpenRouter-side failure to :class:`AppError(LLM_UNAVAILABLE)`."""

    # Import lazily so modules can be imported without the SDK installed.
    # When the SDK is missing, bind each symbol to a sentinel class so that
    # `isinstance(exc, X)` stays well-typed and always returns False.
    try:
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            RateLimitError,
        )
    except ImportError:  # pragma: no cover — openai is a hard dep

        class _Missing(Exception):
            """Placeholder used when the openai SDK is unavailable."""

        APIConnectionError = _Missing  # type: ignore[assignment,misc]
        APIStatusError = _Missing  # type: ignore[assignment,misc]
        APITimeoutError = _Missing  # type: ignore[assignment,misc]
        AuthenticationError = _Missing  # type: ignore[assignment,misc]
        BadRequestError = _Missing  # type: ignore[assignment,misc]
        RateLimitError = _Missing  # type: ignore[assignment,misc]

    # Re-raise AppErrors untouched — they already carry the right code.
    if isinstance(exc, AppError):
        raise exc

    details: dict[str, Any] = {}
    message = "The OpenRouter LLM is currently unavailable."
    if isinstance(exc, AuthenticationError):
        message = "OpenRouter authentication failed. Check OPENROUTER_API_KEY."
        details["reason"] = "auth"
    elif isinstance(exc, RateLimitError):
        message = "OpenRouter rate limit hit. Try again shortly."
        details["reason"] = "rate_limit"
    elif isinstance(exc, APITimeoutError):
        message = "OpenRouter request timed out."
        details["reason"] = "timeout"
    elif isinstance(exc, APIConnectionError):
        message = "Could not reach the OpenRouter API."
        details["reason"] = "connection"
    elif isinstance(exc, BadRequestError):
        message = "OpenRouter rejected the chat payload."
        details["reason"] = "bad_request"
    elif isinstance(exc, APIStatusError):
        message = f"OpenRouter returned an error status ({getattr(exc, 'status_code', 'n/a')})."
        details["reason"] = "status_error"
    else:
        details["reason"] = exc.__class__.__name__

    logger.info("openrouter: %s (%s)", message, details.get("reason"))
    raise AppError(_llm_code(), message, details) from exc


# Legacy alias so existing tests can keep importing OpenAIChatClient while we
# migrate their assertions. Removed in a follow-up PR.
OpenAIChatClient = OpenRouterChatClient


__all__ = [
    "MAX_HISTORY_TURNS",
    "MAX_OUTPUT_TOKENS",
    "MODEL_SLUG_RE",
    "OpenAIChatClient",
    "OpenRouterChatClient",
    "build_openai_client",
    "build_openrouter_client",
    "validate_model_slug",
]
