"""High-level orchestrator for ``POST /api/chat``."""

from __future__ import annotations

import logging
from typing import Any

from app.errors import AppError
from app.schemas import (
    ChatCitation,
    ChatContext,
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
from app.services.chat.tools import ChatToolbox

logger = logging.getLogger(__name__)


class ChatService:
    """Orchestrates the hybrid chat engine."""

    def __init__(
        self,
        llm: OpenRouterChatClient | None = None,
        *,
        toolbox: ChatToolbox | None = None,
    ) -> None:
        self._llm = llm
        self._toolbox = toolbox

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
        chat_context: ChatContext | None = None,
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
            return await self._answer_with_llm(
                messages,
                context,
                chat_context=chat_context,
                model=model,
            )

        known = list(context.orp.weights.keys()) if context is not None else []
        match = classify_intent(last_user.content, known_tickers=known)
        if match is not None:
            answer, citations = render_rule_answer(match, context, messages)
            citations = [
                citation
                if citation.source_type is not None
                else citation.model_copy(update={"source_type": "rule"})
                for citation in citations
            ]
            logger.info("chat: rule hit intent=%s ticker=%s", match.intent.value, match.ticker)
            return ChatResponse(answer=answer, source=ChatSource.RULE, citations=citations)

        if mode == ChatMode.AUTO and self._llm is not None:
            logger.info("chat: rule miss, falling back to LLM")
            return await self._answer_with_llm(
                messages,
                context,
                chat_context=chat_context,
                model=model,
            )

        miss, citations = rule_miss_answer(mode.value)
        return ChatResponse(answer=miss, source=ChatSource.RULE, citations=citations)

    async def _answer_with_llm(
        self,
        messages: list[ChatMessage],
        context: OptimizationResult | None,
        *,
        chat_context: ChatContext | None = None,
        model: str | None = None,
    ) -> ChatResponse:
        if self._llm is None:
            raise AppError(
                ErrorCode.LLM_UNAVAILABLE,
                "The OpenRouter LLM is not configured on this backend.",
                {"reason": "openrouter_api_key_missing"},
            )
        try:
            raw_result: Any = await self._llm.answer(
                messages,
                context,
                model=model,
                chat_context=chat_context,
                toolbox=self._toolbox,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            raw_result = await self._llm.answer(messages, context, model=model)
        citations: list[ChatCitation] = []
        tool_invocations: list[str] = []
        if hasattr(raw_result, "answer"):
            answer = str(raw_result.answer)
            model_used = str(raw_result.model_used)
            citations = list(getattr(raw_result, "citations", []))
            tool_invocations = list(getattr(raw_result, "tool_invocations", []))
        elif isinstance(raw_result, tuple):
            answer, model_used = raw_result
        else:  # pragma: no cover
            answer, model_used = str(raw_result), (model or self._llm.model)
        return ChatResponse(
            answer=answer,
            source=ChatSource.LLM,
            citations=citations or _llm_context_citations(context, chat_context, model_used),
            tool_invocations=tool_invocations,
        )


def _last_user_message(messages: list[ChatMessage]) -> ChatMessage | None:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg
    return None


def _llm_context_citations(
    context: OptimizationResult | None,
    chat_context: ChatContext | None = None,
    model_used: str | None = None,
) -> list[ChatCitation]:
    citations: list[ChatCitation] = []
    if model_used:
        citations.append(ChatCitation(label="model", value=model_used, source_type="llm"))
    snapshot = chat_context.portfolio_snapshot if chat_context is not None else None
    if snapshot is not None and snapshot.orp_sharpe is not None:
        citations.append(
            ChatCitation(
                label="ORP Sharpe",
                value=f"{snapshot.orp_sharpe:.4f}",
                source_type="context",
                as_of=snapshot.as_of.isoformat() if snapshot.as_of else None,
            )
        )
    if context is None:
        return citations
    orp = context.orp
    comp = context.complete
    citations.extend(
        [
            ChatCitation(
                label="ORP expected return",
                value=f"{orp.expected_return:.4f}",
                source_type="context",
                as_of=context.as_of.isoformat(),
            ),
            ChatCitation(
                label="ORP std dev",
                value=f"{orp.std_dev:.4f}",
                source_type="context",
                as_of=context.as_of.isoformat(),
            ),
            ChatCitation(
                label="ORP Sharpe",
                value=f"{orp.sharpe:.4f}",
                source_type="context",
                as_of=context.as_of.isoformat(),
            ),
            ChatCitation(
                label="y*",
                value=f"{comp.y_star:.4f}",
                source_type="context",
                as_of=context.as_of.isoformat(),
            ),
            ChatCitation(
                label="risk-free rate",
                value=f"{context.risk_free_rate:.4f}",
                source_type="context",
                as_of=context.as_of.isoformat(),
            ),
        ]
    )
    return citations


__all__ = ["ChatService"]
