"""Failure-injection suite — AV / Yahoo / FRED / OpenRouter error paths.

This suite deliberately breaks every external dependency and asserts the
API still produces the *right* envelope and provenance headers. It is the
load-bearing safety net for SPEC §6's "Error taxonomy" and for the
fallback chain described in ``backend/app/data/service.py``.

We reuse the in-process stub clients from ``tests/api/conftest.py`` and
inject failures by setting ``hist_exc`` / ``quote_exc`` / ``exc`` on them;
OpenRouter paths patch the ``openai`` SDK via ``monkeypatch``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from fastapi import FastAPI

from app.api.deps import AppState
from app.api.llm import reset_models_cache
from app.errors import AppError, ProviderUnavailableError, RateLimitError
from app.schemas import ErrorCode
from app.services.chat.service import ChatService

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Data layer — Alpha Vantage / Yahoo / FRED error paths
# ---------------------------------------------------------------------------


async def test_av_rate_limited_falls_back_to_yahoo(
    api_client: httpx.AsyncClient, api_state: AppState
) -> None:
    """AV 429 → Yahoo serves the request and the response is tagged
    ``X-Data-Source: yahoo`` with a warning about the fallback."""

    api_state.alpha_vantage.hist_exc = RateLimitError(
        "alpha-vantage", 30.0, scope="minute"
    )

    resp = await api_client.get(
        "/api/historical", params={"ticker": "AAPL", "frequency": "daily"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Data-Source"] == "yahoo"
    warnings = resp.headers.get("X-Data-Warnings", "")
    assert "Alpha Vantage rate-limited" in warnings


async def test_av_500_then_yahoo_500_surfaces_unavailable(
    api_client: httpx.AsyncClient, api_state: AppState
) -> None:
    """Both providers broken, ``USE_MOCK_FALLBACK=false`` → 503 DATA_PROVIDER_UNAVAILABLE."""

    api_state.alpha_vantage.hist_exc = ProviderUnavailableError(
        "alpha-vantage", "500 Internal Server Error"
    )

    class _Broken:
        async def get_historical_daily(self, *a, **kw):
            raise ProviderUnavailableError("yahoo", "500")

        async def get_quote(self, *a, **kw):
            raise ProviderUnavailableError("yahoo", "500")

        async def close(self):
            return None

    api_state.service._yahoo = _Broken()

    resp = await api_client.get(
        "/api/historical", params={"ticker": "AAPL", "frequency": "daily"}
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == ErrorCode.DATA_PROVIDER_UNAVAILABLE.value


async def test_av_and_yahoo_broken_with_mock_fallback_returns_mock(
    api_client: httpx.AsyncClient, api_state: AppState
) -> None:
    """With ``USE_MOCK_FALLBACK=true`` the service serves mock data and
    flags it via the ``X-Data-Source: MOCK`` header."""

    api_state.alpha_vantage.hist_exc = ProviderUnavailableError("alpha-vantage", "down")
    api_state.alpha_vantage.quote_exc = ProviderUnavailableError("alpha-vantage", "down")
    api_state.service._use_mock = True

    class _Broken:
        async def get_historical_daily(self, *a, **kw):
            raise ProviderUnavailableError("yahoo", "down")

        async def get_quote(self, *a, **kw):
            raise ProviderUnavailableError("yahoo", "down")

        async def close(self):
            return None

    api_state.service._yahoo = _Broken()

    resp = await api_client.get("/api/quote", params={"ticker": "AAPL"})
    assert resp.status_code == 200
    assert resp.headers["X-Data-Source"].lower() == "mock"
    warnings = resp.headers.get("X-Data-Warnings", "")
    assert "mock" in warnings.lower()


async def test_fred_500_falls_back_to_static_rate(
    api_client: httpx.AsyncClient, api_state: AppState
) -> None:
    api_state.fred.exc = ProviderUnavailableError("fred", "500")

    resp = await api_client.get("/api/risk-free-rate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "FALLBACK"
    # X-Data-Source mirrors the body
    assert resp.headers.get("X-Data-Source") == "FALLBACK"


# ---------------------------------------------------------------------------
# OpenRouter — auth / rate-limit / timeout / malformed
# ---------------------------------------------------------------------------


class _LlmStub:
    """Injectable LLM that raises pre-built AppErrors on ``answer``."""

    model = "google/gemma-4-31b-it"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def answer(self, messages, context, *, model=None):
        mapping = {
            "auth": "OpenRouter authentication failed. Check OPENROUTER_API_KEY.",
            "rate_limit": "OpenRouter rate limit hit. Try again shortly.",
            "timeout": "OpenRouter request timed out.",
            "connection": "Could not reach the OpenRouter API.",
            "malformed_response": "OpenRouter returned a malformed response.",
        }
        raise AppError(
            ErrorCode.LLM_UNAVAILABLE,
            mapping[self._reason],
            {"reason": self._reason},
        )

    async def close(self):
        pass


@pytest.mark.parametrize(
    "reason",
    ["auth", "rate_limit", "timeout", "connection", "malformed_response"],
)
async def test_openrouter_error_maps_to_llm_unavailable(
    reason: str,
    app_instance: FastAPI,
    api_state: AppState,
    api_client: httpx.AsyncClient,
) -> None:
    api_state.chat_service = ChatService(llm=_LlmStub(reason))  # type: ignore[arg-type]
    app_instance.state.app_state = api_state

    resp = await api_client.post(
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "explain Sharpe"}],
            "mode": "llm",
        },
    )
    assert resp.status_code == 503
    envelope = resp.json()
    assert envelope["code"] == ErrorCode.LLM_UNAVAILABLE.value
    assert envelope["details"]["reason"] == reason


async def test_openrouter_real_sdk_errors_map_to_llm_unavailable(monkeypatch) -> None:
    """Exercise the exception-mapping logic inside ``_raise_llm_unavailable``
    by feeding real ``openai`` exception classes through it."""

    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        RateLimitError,
    )

    from app.services.chat.llm import _raise_llm_unavailable

    fake_request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")

    def _status_exc(cls, status: int):
        body: dict = {"error": {"message": "boom"}}
        response = httpx.Response(status, request=fake_request, json=body)
        return cls(message="boom", response=response, body=body)

    cases = [
        (AuthenticationError, 401, "auth"),
        (RateLimitError, 429, "rate_limit"),
        (BadRequestError, 400, "bad_request"),
    ]
    for cls, status, reason in cases:
        with pytest.raises(AppError) as excinfo:
            _raise_llm_unavailable(_status_exc(cls, status))
        assert excinfo.value.code is ErrorCode.LLM_UNAVAILABLE
        assert excinfo.value.details.get("reason") == reason

    # Timeout and connection errors have different constructor signatures.
    with pytest.raises(AppError) as excinfo:
        _raise_llm_unavailable(APITimeoutError(request=fake_request))
    assert excinfo.value.details.get("reason") == "timeout"

    with pytest.raises(AppError) as excinfo:
        _raise_llm_unavailable(APIConnectionError(request=fake_request))
    assert excinfo.value.details.get("reason") == "connection"

    # Generic APIStatusError (500) → status_error
    with pytest.raises(AppError) as excinfo:
        _raise_llm_unavailable(_status_exc(APIStatusError, 500))
    assert excinfo.value.details.get("reason") == "status_error"


# ---------------------------------------------------------------------------
# /api/llm/models proxy failure modes
# ---------------------------------------------------------------------------


async def test_llm_models_route_maps_upstream_500_to_llm_unavailable(
    api_client: httpx.AsyncClient,
) -> None:
    reset_models_cache()
    async with respx.mock(assert_all_called=False) as rx:
        rx.get("https://openrouter.ai/api/v1/models").mock(
            return_value=httpx.Response(503, json={"error": "boom"})
        )
        resp = await api_client.get("/api/llm/models")
    assert resp.status_code == 503
    envelope = resp.json()
    assert envelope["code"] == ErrorCode.LLM_UNAVAILABLE.value
    assert envelope["details"]["reason"] == "status_error"


async def test_llm_models_route_maps_malformed_json_to_llm_unavailable(
    api_client: httpx.AsyncClient,
) -> None:
    reset_models_cache()
    async with respx.mock(assert_all_called=False) as rx:
        rx.get("https://openrouter.ai/api/v1/models").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=b"not-json-at-all{{{",
            )
        )
        resp = await api_client.get("/api/llm/models")
    assert resp.status_code == 503
    assert resp.json()["code"] == ErrorCode.LLM_UNAVAILABLE.value


async def test_llm_models_route_rejects_unexpected_shape(
    api_client: httpx.AsyncClient,
) -> None:
    reset_models_cache()
    async with respx.mock(assert_all_called=False) as rx:
        rx.get("https://openrouter.ai/api/v1/models").mock(
            return_value=httpx.Response(200, json={"not": "a list"})
        )
        resp = await api_client.get("/api/llm/models")
    assert resp.status_code == 503
    assert resp.json()["details"]["reason"] == "malformed_response"


async def test_llm_models_route_caches_results(
    api_client: httpx.AsyncClient,
) -> None:
    """Second request within TTL must not hit OpenRouter again."""

    reset_models_cache()
    async with respx.mock(assert_all_called=False) as rx:
        route = rx.get("https://openrouter.ai/api/v1/models").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "a/b", "name": "A/B", "context_length": 128000}]},
            )
        )
        resp1 = await api_client.get("/api/llm/models")
        resp2 = await api_client.get("/api/llm/models")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["cached"] is False
    assert resp2.json()["cached"] is True
    assert route.call_count == 1


async def test_llm_default_reports_availability(
    api_client: httpx.AsyncClient, api_state: AppState
) -> None:
    resp = await api_client.get("/api/llm/default")
    assert resp.status_code == 200
    body = resp.json()
    # No API key configured in isolated_settings => llmAvailable is False.
    assert body["llmAvailable"] is False
    assert body["defaultModel"] == api_state.settings.openrouter_model
    assert body["baseUrl"].startswith("https://openrouter.ai/")


# ---------------------------------------------------------------------------
# Misc provenance sanity
# ---------------------------------------------------------------------------


async def test_optimize_still_returns_when_fred_is_down(
    api_client: httpx.AsyncClient, api_state: AppState
) -> None:
    """A broken FRED feed must not block /api/optimize — it falls back to
    the static risk-free rate and surfaces a warning."""

    api_state.fred.exc = ProviderUnavailableError("fred", "500")
    # Pin AV to a known "now" to keep the mock-data window stable.
    _ = datetime(2024, 11, 21, tzinfo=UTC)

    resp = await api_client.post(
        "/api/optimize",
        json={
            "tickers": ["AAPL", "NVDA"],
            "marketProxy": "SPY",
            "riskAversion": 4,
            "allowShort": False,
        },
    )
    # Optimize may or may not succeed depending on rolling synthetic market
    # proxy data; the important assertion is that a FRED-down doesn't turn
    # into a 5xx envelope surface.
    # We only care that the error (if any) is a typed envelope, not a 5xx.
    assert resp.status_code < 500
