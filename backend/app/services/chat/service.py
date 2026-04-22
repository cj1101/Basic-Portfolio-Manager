"""High-level orchestrator for ``POST /api/chat``.

The service decides between the rule engine and the LLM based on the
user-selected :class:`~app.schemas.ChatMode` and the presence of an
``OpenAIChatClient``:

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
from app.services.chat.llm import OpenAIChatClient
from app.services.chat.rules import render_rule_answer, rule_miss_answer

logger = logging.getLogger(__name__)


class ChatService:
    """Orchestrates the hybrid chat engine."""

    def __init__(self, llm: OpenAIChatClient | None = None) -> None:
        self._llm = llm

    @property
    def llm_available(self) -> bool:
        return self._llm is not None

    async def answer(
        self,
        messages: list[ChatMessage],
        context: OptimizationResult | None,
        mode: ChatMode = ChatMode.AUTO,
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
            return await self._answer_with_llm(messages, context)

        # rule or auto: always attempt classification first.
        known = list(context.orp.weights.keys()) if context is not None else []
        match = classify_intent(last_user.content, known_tickers=known)
        if match is not None:
            answer, citations = render_rule_answer(match, context, messages)
            logger.info("chat: rule hit intent=%s ticker=%s", match.intent.value, match.ticker)
            return ChatResponse(answer=answer, source=ChatSource.RULE, citations=citations)

        if mode == ChatMode.AUTO and self._llm is not None:
            logger.info("chat: rule miss, falling back to LLM")
            return await self._answer_with_llm(messages, context)

        miss, citations = rule_miss_answer(mode.value)
        return ChatResponse(answer=miss, source=ChatSource.RULE, citations=citations)

    async def _answer_with_llm(
        self,
        messages: list[ChatMessage],
        context: OptimizationResult | None,
    ) -> ChatResponse:
        if self._llm is None:
            raise AppError(
                ErrorCode.LLM_UNAVAILABLE,
                "The OpenAI LLM is not configured on this backend.",
                {"reason": "openai_api_key_missing"},
            )
        answer = await self._llm.answer(messages, context)
        return ChatResponse(
            answer=answer,
            source=ChatSource.LLM,
            citations=_llm_context_citations(context),
        )


def _last_user_message(messages: list[ChatMessage]) -> ChatMessage | None:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg
    return None


def _llm_context_citations(context: OptimizationResult | None) -> list[ChatCitation]:
    """Publish the high-level portfolio numbers the LLM was given.

    Even though the LLM may or may not use them, surfacing the canonical
    inputs gives the user provenance over what the model saw — identical to
    how rule answers cite every scalar they mention.
    """

    if context is None:
        return []
    orp = context.orp
    comp = context.complete
    return [
        ChatCitation(label="ORP expected return", value=f"{orp.expected_return:.4f}"),
        ChatCitation(label="ORP std dev", value=f"{orp.std_dev:.4f}"),
        ChatCitation(label="ORP Sharpe", value=f"{orp.sharpe:.4f}"),
        ChatCitation(label="y*", value=f"{comp.y_star:.4f}"),
        ChatCitation(label="risk-free rate", value=f"{context.risk_free_rate:.4f}"),
    ]


__all__ = ["ChatService"]
