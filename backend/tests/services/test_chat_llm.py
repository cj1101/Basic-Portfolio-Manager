"""Agent E — OpenAI client wrapper tests (respx-mocked)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.errors import AppError
from app.schemas import ChatMessage, ErrorCode, OptimizationResult
from app.services.chat.llm import (
    MAX_HISTORY_TURNS,
    OpenAIChatClient,
    _serialize_context,
    build_openai_client,
)
from app.settings import Settings


_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _make_client() -> OpenAIChatClient:
    return OpenAIChatClient(
        "test-key",
        model="gpt-4o-mini",
        timeout_seconds=2.0,
    )


def _completion(content: str) -> dict:
    return {
        "id": "cmpl_test",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


@respx.mock
async def test_answer_happy_path(
    sample_optimization_result: OptimizationResult,
):
    route = respx.post(_OPENAI_URL).respond(
        200, json=_completion("Your Sharpe is 0.77.")
    )
    client = _make_client()
    try:
        answer = await client.answer(
            [ChatMessage(role="user", content="what is my Sharpe?")],
            sample_optimization_result,
        )
    finally:
        await client.close()

    assert answer == "Your Sharpe is 0.77."
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "gpt-4o-mini"
    # Last user message should carry the portfolio JSON blob + the question.
    last = body["messages"][-1]
    assert last["role"] == "user"
    assert "Portfolio snapshot" in last["content"]
    assert "what is my Sharpe" in last["content"]


@respx.mock
async def test_answer_empty_messages_raises():
    client = _make_client()
    try:
        with pytest.raises(AppError) as exc_info:
            await client.answer([], None)
    finally:
        await client.close()
    assert exc_info.value.code is ErrorCode.LLM_UNAVAILABLE


@respx.mock
async def test_answer_history_is_bounded(
    sample_optimization_result: OptimizationResult,
):
    route = respx.post(_OPENAI_URL).respond(
        200, json=_completion("bounded reply.")
    )
    client = _make_client()
    # Build a ridiculous 25-turn history; only the last MAX_HISTORY_TURNS should be sent.
    messages = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg {i}")
        for i in range(25)
    ]
    try:
        await client.answer(messages, sample_optimization_result)
    finally:
        await client.close()

    body = json.loads(route.calls.last.request.content)
    # System + MAX_HISTORY_TURNS turns (the last one gets the snapshot appended).
    assert len(body["messages"]) == MAX_HISTORY_TURNS + 1


@respx.mock
async def test_answer_auth_error_mapped(
    sample_optimization_result: OptimizationResult,
):
    respx.post(_OPENAI_URL).respond(
        401,
        json={"error": {"message": "Invalid API key", "type": "invalid_request"}},
    )
    client = _make_client()
    try:
        with pytest.raises(AppError) as exc:
            await client.answer(
                [ChatMessage(role="user", content="hi")],
                sample_optimization_result,
            )
    finally:
        await client.close()
    assert exc.value.code is ErrorCode.LLM_UNAVAILABLE
    assert exc.value.details["reason"] == "auth"


@respx.mock
async def test_answer_rate_limit_mapped(
    sample_optimization_result: OptimizationResult,
):
    respx.post(_OPENAI_URL).respond(
        429, json={"error": {"message": "Rate limit"}}
    )
    client = _make_client()
    try:
        with pytest.raises(AppError) as exc:
            await client.answer(
                [ChatMessage(role="user", content="hi")],
                sample_optimization_result,
            )
    finally:
        await client.close()
    assert exc.value.code is ErrorCode.LLM_UNAVAILABLE
    assert exc.value.details["reason"] == "rate_limit"


@respx.mock
async def test_answer_connection_error_mapped(
    sample_optimization_result: OptimizationResult,
):
    respx.post(_OPENAI_URL).mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    client = _make_client()
    try:
        with pytest.raises(AppError) as exc:
            await client.answer(
                [ChatMessage(role="user", content="hi")],
                sample_optimization_result,
            )
    finally:
        await client.close()
    assert exc.value.code is ErrorCode.LLM_UNAVAILABLE
    assert exc.value.details["reason"] == "connection"


@respx.mock
async def test_answer_timeout_mapped(
    sample_optimization_result: OptimizationResult,
):
    respx.post(_OPENAI_URL).mock(side_effect=httpx.ReadTimeout("too slow"))
    client = _make_client()
    try:
        with pytest.raises(AppError) as exc:
            await client.answer(
                [ChatMessage(role="user", content="hi")],
                sample_optimization_result,
            )
    finally:
        await client.close()
    assert exc.value.code is ErrorCode.LLM_UNAVAILABLE
    assert exc.value.details["reason"] == "timeout"


@respx.mock
async def test_answer_empty_body_mapped(
    sample_optimization_result: OptimizationResult,
):
    respx.post(_OPENAI_URL).respond(
        200, json=_completion("")  # blank assistant content
    )
    client = _make_client()
    try:
        with pytest.raises(AppError) as exc:
            await client.answer(
                [ChatMessage(role="user", content="hi")],
                sample_optimization_result,
            )
    finally:
        await client.close()
    assert exc.value.code is ErrorCode.LLM_UNAVAILABLE
    assert exc.value.details["reason"] == "empty_response"


def test_build_openai_client_returns_none_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("CACHE_DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings()
    assert build_openai_client(settings) is None


def test_build_openai_client_returns_instance_with_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("CACHE_DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = Settings()
    client = build_openai_client(settings)
    assert client is not None
    assert client.model == settings.openai_model


def test_serialize_context_none():
    assert _serialize_context(None) == "null"


def test_serialize_context_rounds_floats(
    sample_optimization_result: OptimizationResult,
):
    blob = _serialize_context(sample_optimization_result)
    # The fixture uses Sharpe 0.767 — should appear rounded to 4dp in the blob.
    assert "0.767" in blob
    # Spot-check the CAL risk-free rate rounding (0.0523 stays as-is at 4dp).
    assert "0.0523" in blob
