"""Agent E — OpenRouter client wrapper tests (respx-mocked)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.errors import AppError
from app.schemas import ChatMessage, ErrorCode, OptimizationResult
from app.services.chat.llm import (
    MAX_HISTORY_TURNS,
    OpenRouterChatClient,
    _serialize_context,
    build_openrouter_client,
    validate_model_slug,
)
from app.settings import Settings

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _make_client(model: str = "google/gemma-4-31b-it") -> OpenRouterChatClient:
    return OpenRouterChatClient(
        "test-key",
        model=model,
        timeout_seconds=2.0,
        http_referer="http://localhost:5173",
        app_title="Portfolio Manager",
    )


def _completion(content: str, model: str = "google/gemma-4-31b-it") -> dict:
    return {
        "id": "cmpl_test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
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
    route = respx.post(_OPENROUTER_URL).respond(
        200, json=_completion("Your Sharpe is 0.77.")
    )
    client = _make_client()
    try:
        answer, model_used = await client.answer(
            [ChatMessage(role="user", content="what is my Sharpe?")],
            sample_optimization_result,
        )
    finally:
        await client.close()

    assert answer == "Your Sharpe is 0.77."
    assert model_used == "google/gemma-4-31b-it"
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "google/gemma-4-31b-it"
    # Attribution headers should be sent verbatim.
    headers = route.calls.last.request.headers
    assert headers.get("HTTP-Referer") == "http://localhost:5173"
    assert headers.get("X-Title") == "Portfolio Manager"
    # Last user message should carry the portfolio JSON blob + the question.
    last = body["messages"][-1]
    assert last["role"] == "user"
    assert "Portfolio snapshot" in last["content"]
    assert "what is my Sharpe" in last["content"]


@respx.mock
async def test_answer_per_request_model_override(
    sample_optimization_result: OptimizationResult,
):
    route = respx.post(_OPENROUTER_URL).respond(
        200, json=_completion("override ok.", model="anthropic/claude-3.5-sonnet")
    )
    client = _make_client()
    try:
        answer, model_used = await client.answer(
            [ChatMessage(role="user", content="hi")],
            sample_optimization_result,
            model="anthropic/claude-3.5-sonnet",
        )
    finally:
        await client.close()
    assert answer == "override ok."
    assert model_used == "anthropic/claude-3.5-sonnet"
    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "anthropic/claude-3.5-sonnet"


@respx.mock
async def test_answer_rejects_malicious_model_slug(
    sample_optimization_result: OptimizationResult,
):
    client = _make_client()
    try:
        with pytest.raises(AppError) as exc:
            await client.answer(
                [ChatMessage(role="user", content="hi")],
                sample_optimization_result,
                model="foo\r\nX-Injected: pwn",
            )
    finally:
        await client.close()
    assert exc.value.code is ErrorCode.LLM_UNAVAILABLE
    assert exc.value.details["reason"] == "invalid_model_slug"


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
    route = respx.post(_OPENROUTER_URL).respond(
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
    respx.post(_OPENROUTER_URL).respond(
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
    respx.post(_OPENROUTER_URL).respond(
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
    respx.post(_OPENROUTER_URL).mock(
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
    respx.post(_OPENROUTER_URL).mock(side_effect=httpx.ReadTimeout("too slow"))
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
    respx.post(_OPENROUTER_URL).respond(
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


def test_build_openrouter_client_returns_none_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("CACHE_DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert build_openrouter_client(settings) is None


def test_build_openrouter_client_returns_instance_with_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("CACHE_DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    settings = Settings(_env_file=None)
    client = build_openrouter_client(settings)
    assert client is not None
    assert client.model == settings.openrouter_model


def test_validate_model_slug_accepts_common_forms():
    assert validate_model_slug("google/gemma-4-31b-it") == "google/gemma-4-31b-it"
    assert validate_model_slug("openai/gpt-4o") == "openai/gpt-4o"
    assert validate_model_slug("anthropic/claude-3.5-sonnet:beta") == (
        "anthropic/claude-3.5-sonnet:beta"
    )


def test_validate_model_slug_rejects_newlines():
    with pytest.raises(AppError) as exc:
        validate_model_slug("foo\r\nX-Injected: yes")
    assert exc.value.code is ErrorCode.LLM_UNAVAILABLE


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


# ---------------------------------------------------------------------------
# Live smoke test — gated by RUN_LIVE_TESTS=1 + a real OPENROUTER_API_KEY.
# Running one real round-trip against ``google/gemma-4-31b-it`` so we catch
# regressions in the attribution headers, model slug, or timeout config.
# ---------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_openrouter_round_trip(
    sample_optimization_result: OptimizationResult,
) -> None:
    import os

    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("RUN_LIVE_TESTS=1 required")
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY required for the live smoke test")

    client = OpenRouterChatClient(
        api_key,
        model="google/gemma-4-31b-it",
        timeout_seconds=30.0,
        http_referer="http://localhost:5173",
        app_title="Portfolio Manager (live-smoke)",
    )
    try:
        answer, model = await client.answer(
            [ChatMessage(role="user", content="In one sentence: what is a Sharpe ratio?")],
            sample_optimization_result,
        )
    finally:
        await client.close()
    assert isinstance(answer, str) and answer.strip()
    assert model == "google/gemma-4-31b-it"
