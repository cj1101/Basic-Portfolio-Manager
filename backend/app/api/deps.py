"""FastAPI dependency wiring.

The lifespan in ``app.main`` builds a single ``AppState`` per process; routes
then pull typed dependencies (cache, service, rate limiter) from it via
``Depends``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Depends, Request

if TYPE_CHECKING:  # pragma: no cover
    from app.data.cache import MarketCache
    from app.data.clients.alpha_vantage import AlphaVantageClient
    from app.data.clients.fred import FredClient
    from app.data.clients.yahoo import YahooClient
    from app.data.rate_limit import AlphaVantageRateLimiter
    from app.data.service import DataService
    from app.settings import Settings


@dataclass
class AppState:
    settings: Settings
    cache: MarketCache
    rate_limiter: AlphaVantageRateLimiter
    alpha_vantage: AlphaVantageClient | None
    yahoo: YahooClient
    fred: FredClient | None
    service: DataService


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "app_state", None)
    if state is None:  # pragma: no cover — only happens if lifespan misconfigured
        raise RuntimeError("AppState not initialized")
    return state


def get_service(state: AppState = Depends(get_state)) -> DataService:
    return state.service


def get_settings_dep(state: AppState = Depends(get_state)) -> Settings:
    return state.settings


__all__ = ["AppState", "get_service", "get_settings_dep", "get_state"]
