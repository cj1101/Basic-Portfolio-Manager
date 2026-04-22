"""FastAPI entrypoint for the Phase 1B data layer."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.deps import AppState
from app.api.routes import router as api_router
from app.data.cache import MarketCache
from app.data.chat_store import ChatStore
from app.data.clients.alpha_vantage import AlphaVantageClient
from app.data.clients.fred import FredClient
from app.data.clients.yahoo import YahooClient
from app.data.rate_limit import AlphaVantageRateLimiter
from app.data.service import DataService
from app.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_handler,
)
from app.services.chat.llm import build_openai_client
from app.services.chat.service import ChatService
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


async def build_state(settings: Settings) -> AppState:
    cache = MarketCache(settings.cache_db_path)
    await cache.connect()

    rate_limiter = AlphaVantageRateLimiter(
        cache,
        per_minute=settings.alpha_vantage_requests_per_minute,
        per_day=settings.alpha_vantage_requests_per_day,
    )

    alpha_vantage: AlphaVantageClient | None = None
    if settings.alpha_vantage_api_key:
        alpha_vantage = AlphaVantageClient(
            api_key=settings.alpha_vantage_api_key,
            rate_limiter=rate_limiter,
            base_url=settings.alpha_vantage_base_url,
            timeout=settings.http_timeout_seconds,
        )
    else:
        logger.warning(
            "ALPHA_VANTAGE_API_KEY is not set; Alpha Vantage disabled, only Yahoo fallback active."
        )

    yahoo = YahooClient()

    fred: FredClient | None = None
    if settings.fred_api_key:
        fred = FredClient(
            api_key=settings.fred_api_key,
            base_url=settings.fred_base_url,
            timeout=settings.http_timeout_seconds,
        )

    service = DataService(
        cache=cache,
        alpha_vantage=alpha_vantage,
        yahoo=yahoo,
        fred=fred,
        use_mock_fallback=settings.use_mock_fallback,
        quote_ttl_seconds=settings.quote_cache_ttl_seconds,
        risk_free_rate_ttl_seconds=settings.risk_free_rate_cache_ttl_seconds,
    )

    chat_store = ChatStore(settings.cache_db_path)
    await chat_store.connect()

    openai_client = build_openai_client(settings)
    if openai_client is None:
        logger.info("OPENAI_API_KEY is not set; /api/chat will operate in rule-only mode.")
    chat_service = ChatService(llm=openai_client)

    return AppState(
        settings=settings,
        cache=cache,
        rate_limiter=rate_limiter,
        alpha_vantage=alpha_vantage,
        yahoo=yahoo,
        fred=fred,
        service=service,
        chat_store=chat_store,
        chat_service=chat_service,
    )


async def teardown_state(state: AppState) -> None:
    if state.alpha_vantage is not None:
        await state.alpha_vantage.close()
    if state.fred is not None:
        await state.fred.close()
    await state.yahoo.close()
    if state.chat_service.llm_available:
        # The same AsyncOpenAI instance is held inside the client wrapper.
        llm = state.chat_service._llm  # noqa: SLF001 — clean shutdown only
        if llm is not None:
            await llm.close()
    await state.chat_store.close()
    await state.cache.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.alpha_vantage_api_key:
        # SPEC §7 marks this as "App refuses to start without it". We downgrade
        # to a loud warning when USE_MOCK_FALLBACK is enabled so local demos
        # can still boot; otherwise we fail fast.
        if not settings.use_mock_fallback:
            raise RuntimeError(
                "ALPHA_VANTAGE_API_KEY is required. Set it in .env or enable "
                "USE_MOCK_FALLBACK=true for a local demo."
            )
    state = await build_state(settings)
    app.state.app_state = state
    try:
        yield
    finally:
        await teardown_state(state)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Portfolio Manager — Data Layer",
        version=__version__,
        lifespan=lifespan,
    )

    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Data-Source", "X-Data-Warnings", "Retry-After"],
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()


__all__ = ["app", "build_state", "create_app", "lifespan", "teardown_state"]
