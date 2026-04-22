"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# The static fallback value comes from SPEC §3 #4 (FRED DGS3MO snapshot circa
# 2024-11-20). It is intentionally constant so behaviour is deterministic when
# FRED_API_KEY is missing; the response is tagged source="FALLBACK" so callers
# can see it is not live.
FRED_FALLBACK_RATE: float = 0.0523


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    alpha_vantage_api_key: str = Field(default="", description="Required in production")
    fred_api_key: str | None = None
    openrouter_api_key: str | None = None

    port: int = 8000
    cache_db_path: Path = Path("backend/.cache/market.db")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    use_mock_fallback: bool = False
    run_live_tests: bool = False

    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"
    fred_base_url: str = "https://api.stlouisfed.org/fred/series/observations"

    alpha_vantage_requests_per_minute: int = 5
    alpha_vantage_requests_per_day: int = 500

    historical_cache_ttl_seconds: int = 60 * 60 * 24 * 365  # effectively immutable
    quote_cache_ttl_seconds: int = 60 * 5
    risk_free_rate_cache_ttl_seconds: int = 60 * 60 * 24

    http_timeout_seconds: float = 15.0

    # Chat / LLM (Agent E). We route all LLM calls through OpenRouter because
    # it exposes an OpenAI-compatible API surface while giving the user one
    # billing relationship across 100+ providers. The underlying transport
    # stays the `openai` Python SDK; only the base_url + attribution headers
    # change vs. talking to api.openai.com directly.
    openrouter_model: str = "google/gemma-4-31b-it"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:5173"
    openrouter_app_title: str = "Portfolio Manager"
    chat_llm_timeout_seconds: float = 30.0
    chat_history_limit: int = 100
    llm_models_cache_ttl_seconds: int = 60 * 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def override_settings(settings: Settings) -> None:
    """Test helper — install an explicit Settings instance."""

    global _settings
    _settings = settings


def reset_settings() -> None:
    global _settings
    _settings = None


__all__ = [
    "FRED_FALLBACK_RATE",
    "Settings",
    "get_settings",
    "override_settings",
    "reset_settings",
]
