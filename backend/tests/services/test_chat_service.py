"""Agent E — ChatService orchestration tests."""

from __future__ import annotations

import pytest

from app.errors import AppError
from app.schemas import (
    ChatMessage,
    ChatMode,
    ChatSource,
    ErrorCode,
    OptimizationResult,
)
from app.services.chat.service import ChatService


class _StubLLM:
    """Pretends to be an ``OpenAIChatClient`` without hitting the network."""

    def __init__(self, reply: str = "LLM reply", exc: Exception | None = None):
        self.reply = reply
        self.exc = exc
        self.calls: list[tuple[list[ChatMessage], OptimizationResult | None]] = []

    async def answer(self, messages, context):
        self.calls.append((list(messages), context))
        if self.exc is not None:
            raise self.exc
        return self.reply

    async def close(self) -> None:
        pass


async def test_auto_mode_rule_hit_skips_llm(
    sample_optimization_result: OptimizationResult,
):
    llm = _StubLLM()
    service = ChatService(llm=llm)  # type: ignore[arg-type]
    resp = await service.answer(
        [ChatMessage(role="user", content="what is my Sharpe?")],
        sample_optimization_result,
        ChatMode.AUTO,
    )
    assert resp.source is ChatSource.RULE
    assert llm.calls == []  # never called


async def test_auto_mode_rule_miss_falls_through_to_llm(
    sample_optimization_result: OptimizationResult,
):
    llm = _StubLLM(reply="free-form answer")
    service = ChatService(llm=llm)  # type: ignore[arg-type]
    resp = await service.answer(
        [ChatMessage(role="user", content="how should I think about rebalancing")],
        sample_optimization_result,
        ChatMode.AUTO,
    )
    assert resp.source is ChatSource.LLM
    assert resp.answer == "free-form answer"
    assert llm.calls  # LLM was invoked


async def test_auto_mode_without_llm_returns_rule_miss(
    sample_optimization_result: OptimizationResult,
):
    service = ChatService(llm=None)
    resp = await service.answer(
        [ChatMessage(role="user", content="how should I think about rebalancing")],
        sample_optimization_result,
        ChatMode.AUTO,
    )
    assert resp.source is ChatSource.RULE
    assert "OPENAI_API_KEY" in resp.answer


async def test_rule_mode_never_invokes_llm(
    sample_optimization_result: OptimizationResult,
):
    llm = _StubLLM()
    service = ChatService(llm=llm)  # type: ignore[arg-type]
    resp = await service.answer(
        [ChatMessage(role="user", content="how should I think about rebalancing")],
        sample_optimization_result,
        ChatMode.RULE,
    )
    assert resp.source is ChatSource.RULE
    assert llm.calls == []


async def test_llm_mode_without_client_raises_llm_unavailable(
    sample_optimization_result: OptimizationResult,
):
    service = ChatService(llm=None)
    with pytest.raises(AppError) as exc:
        await service.answer(
            [ChatMessage(role="user", content="what is my Sharpe?")],
            sample_optimization_result,
            ChatMode.LLM,
        )
    assert exc.value.code is ErrorCode.LLM_UNAVAILABLE


async def test_llm_mode_bypasses_rules(
    sample_optimization_result: OptimizationResult,
):
    llm = _StubLLM(reply="forced LLM")
    service = ChatService(llm=llm)  # type: ignore[arg-type]
    resp = await service.answer(
        # "what is my Sharpe" would trivially match a rule; force LLM anyway.
        [ChatMessage(role="user", content="what is my Sharpe")],
        sample_optimization_result,
        ChatMode.LLM,
    )
    assert resp.source is ChatSource.LLM
    assert resp.answer == "forced LLM"
    # Cites portfolio provenance so the UI can show what the LLM was given.
    labels = [c.label for c in resp.citations]
    assert "ORP Sharpe" in labels


async def test_requires_user_message():
    service = ChatService(llm=None)
    with pytest.raises(AppError) as exc:
        await service.answer(
            [ChatMessage(role="assistant", content="hello")],
            None,
            ChatMode.AUTO,
        )
    assert exc.value.code is ErrorCode.INTERNAL


async def test_empty_messages_rejected():
    service = ChatService(llm=None)
    with pytest.raises(AppError):
        await service.answer([], None, ChatMode.AUTO)


async def test_llm_available_property():
    assert ChatService(llm=None).llm_available is False
    assert ChatService(llm=_StubLLM()).llm_available is True  # type: ignore[arg-type]
