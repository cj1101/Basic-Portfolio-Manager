"""Verify the universal envelope for every ErrorCode surfaced by this layer."""

from __future__ import annotations

import pytest

from app.errors import (
    DataProviderError,
    InsufficientHistoryError,
    InvalidReturnWindowError,
    ProviderUnavailableError,
    RateLimitError,
    UnknownTickerError,
)
from app.schemas import ErrorCode

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("exc", "code", "status"),
    [
        (UnknownTickerError("FAKE"), ErrorCode.UNKNOWN_TICKER, 404),
        (
            InsufficientHistoryError("AAPL", 5, 30),
            ErrorCode.INSUFFICIENT_HISTORY,
            422,
        ),
        (
            RateLimitError("alpha-vantage", 30.0, scope="minute"),
            ErrorCode.DATA_PROVIDER_RATE_LIMIT,
            429,
        ),
        (
            ProviderUnavailableError("alpha-vantage", "down"),
            ErrorCode.DATA_PROVIDER_UNAVAILABLE,
            503,
        ),
        (
            InvalidReturnWindowError("bad"),
            ErrorCode.INVALID_RETURN_WINDOW,
            400,
        ),
        (
            DataProviderError(ErrorCode.INTERNAL, "weird"),
            ErrorCode.INTERNAL,
            500,
        ),
    ],
)
async def test_envelope_shape(api_client, api_state, exc, code, status):
    api_state.alpha_vantage.quote_exc = exc

    class _AlsoFail:
        async def get_quote(self, t):
            raise exc

        async def get_historical_daily(self, t, **kw):
            raise exc

        async def close(self):
            return None

    api_state.service._yahoo = _AlsoFail()

    resp = await api_client.get("/api/quote", params={"ticker": "AAPL"})
    assert resp.status_code == status
    body = resp.json()
    assert set(body.keys()) <= {"code", "message", "details"}
    assert body["code"] == code.value
    assert isinstance(body["message"], str) and body["message"]
    if code is ErrorCode.DATA_PROVIDER_RATE_LIMIT:
        assert "Retry-After" in resp.headers
        assert body["details"]["retryAfterSeconds"] == pytest.approx(30.0)
