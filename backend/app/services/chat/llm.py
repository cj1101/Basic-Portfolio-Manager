"""Thin async wrapper around OpenRouter's OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.errors import AppError
from app.schemas import ChatCitation, ChatContext, ChatMessage, OptimizationResult
from app.services.chat.tools import ChatToolbox
from app.settings import Settings

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS: int = 10
MAX_OUTPUT_TOKENS: int = 700
MAX_TOOL_ROUNDS: int = 4

MODEL_SLUG_RE: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-._:/]{0,99}$")

_SYSTEM_PROMPT = (
    "You are the Portfolio Manager analysis copilot. Be a concise analyst explainer: "
    "ground answers in the provided live portfolio context and any tool outputs, cite the exact "
    "numbers you use, mention freshness or assumptions when relevant, and do not give "
    "personalized investment advice. Use tools when the user asks about hypotheticals, "
    "valuation, analytics, prices, history, or anything not directly answered by the compact "
    "context. Do not call tools that mutate settings or data because none are available. "
    "Stay answer-focused and avoid proactive suggestions unless clarification is required."
)


@dataclass(slots=True)
class LLMAnswer:
    answer: str
    model_used: str
    citations: list[ChatCitation] = field(default_factory=list)
    tool_invocations: list[str] = field(default_factory=list)

    def __iter__(self):
        yield self.answer
        yield self.model_used


def validate_model_slug(slug: str) -> str:
    if not MODEL_SLUG_RE.match(slug):
        raise AppError(
            _llm_code(),
            "Invalid model identifier.",
            {"reason": "invalid_model_slug", "value": slug[:120]},
        )
    return slug


class OpenRouterChatClient:
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
        from openai import AsyncOpenAI

        self._default_model = validate_model_slug(model)
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
        chat_context: ChatContext | None = None,
        toolbox: ChatToolbox | None = None,
    ) -> LLMAnswer:
        bounded = messages[-MAX_HISTORY_TURNS:]
        if not bounded:
            raise AppError(_llm_code(), "Cannot call the LLM with an empty message list.")

        chosen = validate_model_slug(model) if model else self._default_model
        payload = _initial_payload(bounded, context, chat_context)
        tool_defs = toolbox.definitions() if toolbox is not None else None
        citations: list[ChatCitation] = []
        tool_invocations: list[str] = []

        logger.info("openrouter: chat request model=%s msgs=%d", chosen, len(payload))
        for _ in range(MAX_TOOL_ROUNDS + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": chosen,
                    "messages": payload,  # type: ignore[arg-type]
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "temperature": 0.2,
                }
                if tool_defs:
                    kwargs["tools"] = tool_defs
                    kwargs["tool_choice"] = "auto"
                response = await self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                _raise_llm_unavailable(exc)

            try:
                message = response.choices[0].message
            except (IndexError, AttributeError) as exc:
                logger.warning("openrouter: malformed completion response: %s", exc)
                raise AppError(
                    _llm_code(),
                    "OpenRouter returned a malformed response.",
                    {"reason": "malformed_response"},
                ) from exc

            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls and toolbox is not None:
                payload.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.function.name,
                                    "arguments": call.function.arguments,
                                },
                            }
                            for call in tool_calls
                        ],
                    }
                )
                for call in tool_calls:
                    name = call.function.name
                    args = _parse_tool_args(call.function.arguments)
                    tool_result = await toolbox.execute(
                        name,
                        args,
                        chat_context=chat_context,
                        context=context,
                    )
                    tool_invocations.append(name)
                    citations.extend(tool_result.citations)
                    payload.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(tool_result.payload, separators=(",", ":")),
                        }
                    )
                continue

            answer = (message.content or "").strip()
            if not answer:
                raise AppError(
                    _llm_code(),
                    "OpenRouter returned an empty answer.",
                    {"reason": "empty_response"},
                )
            return LLMAnswer(
                answer=answer,
                model_used=chosen,
                citations=_dedupe_citations(citations),
                tool_invocations=tool_invocations,
            )

        raise AppError(
            _llm_code(),
            "OpenRouter exceeded the chat tool-call limit.",
            {"reason": "tool_round_limit"},
        )


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


build_openai_client = build_openrouter_client


def _initial_payload(
    messages: list[ChatMessage],
    context: OptimizationResult | None,
    chat_context: ChatContext | None,
) -> list[dict[str, Any]]:
    last_user = messages[-1]
    compact_context = _serialize_compact_context(chat_context, context)
    user_content = (
        f"Portfolio snapshot / live context (JSON):\n{compact_context}\n\n"
        f"User question:\n{last_user.content}"
    )
    payload: list[dict[str, Any]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for msg in messages[:-1]:
        payload.append({"role": msg.role, "content": msg.content})
    payload.append({"role": "user", "content": user_content})
    return payload


def _serialize_compact_context(
    chat_context: ChatContext | None,
    context: OptimizationResult | None,
) -> str:
    if chat_context is not None:
        return json.dumps(
            _round_floats(
                chat_context.model_dump(mode="json", by_alias=True, exclude_none=True), 4
            ),
            separators=(",", ":"),
        )
    return _serialize_context(context)


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


def _parse_tool_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            _llm_code(),
            "OpenRouter emitted malformed tool arguments.",
            {"reason": "malformed_tool_arguments"},
        ) from exc
    return data if isinstance(data, dict) else {}


def _dedupe_citations(citations: list[ChatCitation]) -> list[ChatCitation]:
    seen: set[tuple[str, str, str | None, str | None]] = set()
    out: list[ChatCitation] = []
    for citation in citations:
        key = (citation.label, citation.value, citation.tool_name, citation.scope)
        if key in seen:
            continue
        seen.add(key)
        out.append(citation)
    return out


def _llm_code():
    from app.schemas import ErrorCode

    return ErrorCode.LLM_UNAVAILABLE


def _raise_llm_unavailable(exc: BaseException) -> None:
    try:
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            RateLimitError,
        )
    except ImportError:  # pragma: no cover

        class _Missing(Exception):
            pass

        APIConnectionError = _Missing  # type: ignore[assignment,misc]
        APIStatusError = _Missing  # type: ignore[assignment,misc]
        APITimeoutError = _Missing  # type: ignore[assignment,misc]
        AuthenticationError = _Missing  # type: ignore[assignment,misc]
        BadRequestError = _Missing  # type: ignore[assignment,misc]
        RateLimitError = _Missing  # type: ignore[assignment,misc]

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


OpenAIChatClient = OpenRouterChatClient


__all__ = [
    "MAX_HISTORY_TURNS",
    "MAX_OUTPUT_TOKENS",
    "MODEL_SLUG_RE",
    "LLMAnswer",
    "OpenAIChatClient",
    "OpenRouterChatClient",
    "_serialize_context",
    "build_openai_client",
    "build_openrouter_client",
    "validate_model_slug",
]
