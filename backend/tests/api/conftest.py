"""API-level fixtures: a FastAPI app wired with stubbed data clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.deps import AppState
from app.api.routes import router as api_router
from app.data.cache import MarketCache
from app.data.chat_store import ChatStore
from app.data.mock import generate_daily_bars
from app.data.rate_limit import AlphaVantageRateLimiter
from app.data.service import DataService
from app.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_handler,
)
from app.services.chat.service import ChatService
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


class StubAV:
    def __init__(self):
        self.hist_exc = None
        self.quote_exc = None

    async def get_historical_daily(self, ticker: str, **kwargs):
        if self.hist_exc:
            raise self.hist_exc
        return generate_daily_bars(ticker, lookback_years=5)

    async def get_quote(self, ticker: str):
        if self.quote_exc:
            raise self.quote_exc
        return {
            "ticker": ticker,
            "price": 228.52,
            "as_of": datetime(2024, 11, 21, tzinfo=timezone.utc),
        }

    async def close(self) -> None:
        return None


class StubYahoo:
    async def get_historical_daily(self, ticker, *, lookback_years, end=None):
        return generate_daily_bars(ticker, lookback_years=lookback_years, end=end)

    async def get_quote(self, ticker):
        return {
            "ticker": ticker,
            "price": 227.10,
            "as_of": datetime(2024, 11, 21, tzinfo=timezone.utc),
        }

    async def close(self) -> None:
        return None


class StubFred:
    def __init__(self):
        self.exc = None

    async def get_latest_dgs3mo(self):
        if self.exc:
            raise self.exc
        return {
            "rate": 0.0462,
            "as_of": datetime(2024, 11, 20, tzinfo=timezone.utc),
            "source": "FRED",
        }

    async def close(self) -> None:
        return None


@pytest_asyncio.fixture
async def api_state(cache: MarketCache, isolated_settings) -> AsyncIterator[AppState]:
    av = StubAV()
    yahoo = StubYahoo()
    fred = StubFred()
    rate_limiter = AlphaVantageRateLimiter(cache, per_minute=100, per_day=10_000)
    service = DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=yahoo,
        fred=fred,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )
    chat_store = ChatStore(isolated_settings.cache_db_path)
    await chat_store.connect()
    chat_service = ChatService(llm=None)
    state = AppState(
        settings=isolated_settings,
        cache=cache,
        rate_limiter=rate_limiter,
        alpha_vantage=av,  # type: ignore[arg-type]
        yahoo=yahoo,  # type: ignore[arg-type]
        fred=fred,  # type: ignore[arg-type]
        service=service,
        chat_store=chat_store,
        chat_service=chat_service,
    )
    try:
        yield state
    finally:
        await chat_store.close()


@pytest_asyncio.fixture
async def app_instance(api_state: AppState) -> FastAPI:
    app = FastAPI()
    app.state.app_state = api_state
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(api_router)
    return app


@pytest_asyncio.fixture
async def api_client(app_instance: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = ASGITransport(app=app_instance)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
