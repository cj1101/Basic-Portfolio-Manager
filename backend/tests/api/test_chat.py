"""Agent E — ``POST /api/chat`` + session endpoint integration tests."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import AppState
from app.errors import AppError
from app.schemas import ChatMessage, ChatMode, ChatSource, ErrorCode
from app.services.chat.service import ChatService


def _sample_context_dict() -> dict:
    return {
        "requestId": "opt_test",
        "asOf": datetime(2025, 4, 1, tzinfo=UTC).isoformat(),
        "riskFreeRate": 0.05,
        "market": {"expectedReturn": 0.10, "stdDev": 0.18, "variance": 0.0324},
        "stocks": [
            {
                "ticker": "AAPL",
                "expectedReturn": 0.21,
                "stdDev": 0.27,
                "beta": 1.22,
                "alpha": 0.04,
                "firmSpecificVar": 0.03,
                "nObservations": 1258,
            },
            {
                "ticker": "NVDA",
                "expectedReturn": 0.44,
                "stdDev": 0.41,
                "beta": 1.63,
                "alpha": 0.22,
                "firmSpecificVar": 0.091,
                "nObservations": 1258,
            },
        ],
        "covariance": {
            "tickers": ["AAPL", "NVDA"],
            "matrix": [[0.0729, 0.061], [0.061, 0.1681]],
        },
        "orp": {
            "weights": {"AAPL": 0.4, "NVDA": 0.6},
            "expectedReturn": 0.33,
            "stdDev": 0.34,
            "variance": 0.1156,
            "sharpe": 0.8235,
        },
        "complete": {
            "yStar": 0.9,
            "weightRiskFree": 0.1,
            "weights": {"AAPL": 0.36, "NVDA": 0.54},
            "expectedReturn": 0.302,
            "stdDev": 0.306,
            "leverageUsed": False,
        },
        "frontierPoints": [{"stdDev": 0.34, "expectedReturn": 0.33}],
        "calPoints": [
            {"stdDev": 0.0, "expectedReturn": 0.05, "y": 0.0},
            {"stdDev": 0.34, "expectedReturn": 0.33, "y": 1.0},
        ],
        "warnings": [],
    }


async def test_chat_rule_mode_happy_path(api_client: httpx.AsyncClient):
    body = {
        "messages": [{"role": "user", "content": "what is my Sharpe?"}],
        "portfolioContext": _sample_context_dict(),
        "mode": "rule",
    }
    resp = await api_client.post("/api/chat", json=body)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["source"] == "rule"
    assert "Sharpe" in payload["answer"] or "sharpe" in payload["answer"]
    assert any(c["label"] == "ORP Sharpe" for c in payload["citations"])


async def test_chat_llm_mode_without_key_returns_503(api_client: httpx.AsyncClient):
    body = {
        "messages": [{"role": "user", "content": "what is my Sharpe?"}],
        "portfolioContext": _sample_context_dict(),
        "mode": "llm",
    }
    resp = await api_client.post("/api/chat", json=body)
    assert resp.status_code == 503
    envelope = resp.json()
    assert envelope["code"] == ErrorCode.LLM_UNAVAILABLE.value


async def test_chat_auto_mode_rule_miss_without_llm(api_client: httpx.AsyncClient):
    body = {
        "messages": [{"role": "user", "content": "how should I think about rebalancing"}],
        "portfolioContext": _sample_context_dict(),
        "mode": "auto",
    }
    resp = await api_client.post("/api/chat", json=body)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "rule"
    assert "OPENROUTER_API_KEY" in payload["answer"]


async def test_chat_auto_mode_fallback_with_llm_stub(
    app_instance: FastAPI, api_state: AppState, api_client: httpx.AsyncClient
):
    class _Stub:
        model = "google/gemma-4-31b-it"

        async def answer(self, messages, context, *, model=None):
            return (
                "Rebalancing is personal — this backend can't advise.",
                model or self.model,
            )

        async def close(self):
            pass

    # Swap in an LLM stub so auto-mode exercises the fallback path.
    api_state.chat_service = ChatService(llm=_Stub())  # type: ignore[arg-type]
    app_instance.state.app_state = api_state

    body = {
        "messages": [{"role": "user", "content": "how should I think about rebalancing"}],
        "portfolioContext": _sample_context_dict(),
        "mode": "auto",
    }
    resp = await api_client.post("/api/chat", json=body)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "llm"
    assert payload["answer"].startswith("Rebalancing is personal")


async def test_chat_session_persistence_end_to_end(
    api_client: httpx.AsyncClient, api_state: AppState
):
    session_id = "session-e2e-1"

    # Send first turn via POST /api/chat with sessionId attached.
    r1 = await api_client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "what is my Sharpe?"}],
            "portfolioContext": _sample_context_dict(),
            "mode": "rule",
            "sessionId": session_id,
        },
    )
    assert r1.status_code == 200

    # Second turn via session-scoped endpoint.
    r2 = await api_client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={
            "messages": [
                {"role": "user", "content": "what is my Sharpe?"},
                {"role": "assistant", "content": r1.json()["answer"]},
                {"role": "user", "content": "explain the efficient frontier"},
            ],
            "portfolioContext": _sample_context_dict(),
            "mode": "rule",
        },
    )
    assert r2.status_code == 200

    # GET the full session and verify both turns are persisted.
    get_resp = await api_client.get(f"/api/chat/sessions/{session_id}")
    assert get_resp.status_code == 200
    session = get_resp.json()
    assert session["sessionId"] == session_id
    # 2 user + 2 assistant turns from the two POSTs.
    roles = [m["role"] for m in session["messages"]]
    assert roles.count("user") == 2
    assert roles.count("assistant") == 2
    for msg in session["messages"]:
        if msg["role"] == "assistant":
            assert msg["source"] == ChatSource.RULE.value

    # DELETE removes the session and the messages.
    del_resp = await api_client.delete(f"/api/chat/sessions/{session_id}")
    assert del_resp.status_code == 204

    reget = await api_client.get(f"/api/chat/sessions/{session_id}")
    assert reget.status_code == 200
    assert reget.json()["messages"] == []


async def test_chat_unknown_session_returns_empty_payload(api_client: httpx.AsyncClient):
    resp = await api_client.get("/api/chat/sessions/nope-nope-nope")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessionId"] == "nope-nope-nope"
    assert body["messages"] == []


async def test_chat_request_validation(api_client: httpx.AsyncClient):
    # Empty message list should be rejected by Pydantic. Backend remaps 422
    # → 400 via ``validation_handler`` for a uniform client surface.
    resp = await api_client.post(
        "/api/chat", json={"messages": [], "mode": "rule"}
    )
    assert resp.status_code == 400


async def test_chat_mode_default_is_auto(api_client: httpx.AsyncClient):
    body = {
        "messages": [{"role": "user", "content": "what is my Sharpe?"}],
        "portfolioContext": _sample_context_dict(),
        # mode omitted → defaults to auto; rules hit first, no LLM needed.
    }
    resp = await api_client.post("/api/chat", json=body)
    assert resp.status_code == 200
    assert resp.json()["source"] == "rule"


async def test_chat_llm_error_envelope_has_details(
    app_instance: FastAPI, api_state: AppState, api_client: httpx.AsyncClient
):
    class _RaisingStub:
        model = "google/gemma-4-31b-it"

        async def answer(self, messages, context, *, model=None):
            raise AppError(
                ErrorCode.LLM_UNAVAILABLE,
                "stub failure",
                {"reason": "rate_limit"},
            )

        async def close(self):
            pass

    api_state.chat_service = ChatService(llm=_RaisingStub())  # type: ignore[arg-type]
    app_instance.state.app_state = api_state

    resp = await api_client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "mode": "llm",
        },
    )
    assert resp.status_code == 503
    envelope = resp.json()
    assert envelope["code"] == ErrorCode.LLM_UNAVAILABLE.value
    assert envelope["details"]["reason"] == "rate_limit"


@pytest.mark.parametrize("mode", ["auto", "rule", "llm"])
async def test_chat_modes_accepted_by_schema(
    mode: str, api_client: httpx.AsyncClient
):
    body = {
        "messages": [{"role": "user", "content": "what is my Sharpe?"}],
        "portfolioContext": _sample_context_dict(),
        "mode": mode,
    }
    resp = await api_client.post("/api/chat", json=body)
    # rule + auto hit the rule engine (200); llm without key returns 503.
    assert resp.status_code in {200, 503}
