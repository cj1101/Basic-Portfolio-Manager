"""High-level orchestrator for ``POST /api/chat``.

The service decides between the rule engine and the LLM based on the
user-selected :class:`~app.schemas.ChatMode` and the presence of an
``OpenRouterChatClient``:

===== =============================================================
mode  behaviour
===== =============================================================
auto  Try rules first. If there is no rule match and the OpenAI
      client is configured, fall through to the LLM. Otherwise
      return the rule-miss template so the UI can surface it.
rule  Rules only. Never call the LLM, even when configured.
llm   Force the LLM path. Raise ``LLM_UNAVAILABLE`` when not
      configured so the frontend can render the 503 banner.
===== =============================================================
"""

from __future__ import annotations

import logging

from app.errors import AppError
from app.schemas import (
    ChatCitation,
    ChatMessage,
    ChatMode,
    ChatResponse,
    ChatSource,
    ErrorCode,
    OptimizationResult,
)
from app.services.chat.intent import classify_intent
from app.services.chat.llm import OpenRouterChatClient
from app.services.chat.rules import render_rule_answer, rule_miss_answer

logger = logging.getLogger(__name__)


class ChatService:
    """Orchestrates the hybrid chat engine."""

    def __init__(self, llm: OpenRouterChatClient | None = None) -> None:
        self._llm = llm

    @property
    def llm_available(self) -> bool:
        return self._llm is not None

    @property
    def default_model(self) -> str | None:
        return self._llm.model if self._llm is not None else None

    async def answer(
        self,
        messages: list[ChatMessage],
        context: OptimizationResult | None,
        mode: ChatMode = ChatMode.AUTO,
        *,
        model: str | None = None,
    ) -> ChatResponse:
        if not messages:
            raise AppError(ErrorCode.INTERNAL, "ChatService.answer requires at least one message.")
        last_user = _last_user_message(messages)
        if last_user is None:
            raise AppError(
                ErrorCode.INTERNAL,
                'The last message must have role="user" for chat routing.',
            )

        if mode == ChatMode.LLM:
            return await self._answer_with_llm(messages, context, model=model)

        # rule or auto: always attempt classification first.
        known = list(context.orp.weights.keys()) if context is not None else []
        match = classify_intent(last_user.content, known_tickers=known)
        if match is not None:
            answer, citations = render_rule_answer(match, context, messages)
            logger.info("chat: rule hit intent=%s ticker=%s", match.intent.value, match.ticker)
            return ChatResponse(answer=answer, source=ChatSource.RULE, citations=citations)

        if mode == ChatMode.AUTO and self._llm is not None:
            logger.info("chat: rule miss, falling back to LLM")
            return await self._answer_with_llm(messages, context, model=model)

        miss, citations = rule_miss_answer(mode.value)
        return ChatResponse(answer=miss, source=ChatSource.RULE, citations=citations)

    async def _answer_with_llm(
        self,
        messages: list[ChatMessage],
        context: OptimizationResult | None,
        *,
        model: str | None = None,
    ) -> ChatResponse:
        if self._llm is None:
            raise AppError(
                ErrorCode.LLM_UNAVAILABLE,
                "The OpenRouter LLM is not configured on this backend.",
                {"reason": "openrouter_api_key_missing"},
            )
        result = await self._llm.answer(messages, context, model=model)
        if isinstance(result, tuple):
            answer, model_used = result
        else:  # pragma: no cover — defensive for test doubles returning a str
            answer, model_used = result, (model or self._llm.model)
        return ChatResponse(
            answer=answer,
            source=ChatSource.LLM,
            citations=_llm_context_citations(context, model_used),
        )


def _last_user_message(messages: list[ChatMessage]) -> ChatMessage | None:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg
    return None


def _llm_context_citations(
    context: OptimizationResult | None,
    model_used: str | None = None,
) -> list[ChatCitation]:
    """Publish the high-level portfolio numbers the LLM was given.

    Even though the LLM may or may not use them, surfacing the canonical
    inputs gives the user provenance over what the model saw — identical to
    how rule answers cite every scalar they mention. When ``model_used`` is
    provided we also publish it so the UI can show "answered by <model>".
    """

    citations: list[ChatCitation] = []
    if model_used:
        citations.append(ChatCitation(label="model", value=model_used))
    if context is None:
        return citations
    orp = context.orp
    comp = context.complete
    citations.extend(
        [
            ChatCitation(label="ORP expected return", value=f"{orp.expected_return:.4f}"),
            ChatCitation(label="ORP std dev", value=f"{orp.std_dev:.4f}"),
            ChatCitation(label="ORP Sharpe", value=f"{orp.sharpe:.4f}"),
            ChatCitation(label="y*", value=f"{comp.y_star:.4f}"),
            ChatCitation(label="risk-free rate", value=f"{context.risk_free_rate:.4f}"),
        ]
    )
    return citations


__all__ = ["ChatService"]
