"""Wire-format types — mirrors docs/CONTRACTS.md §2–§4 field-for-field.

All models serialize to camelCase JSON via ``alias_generator=to_camel``. Python
code always reads the snake_case attribute; the wire format is the camelCase
alias. Non-finite floats are rejected at serialization time per CONTRACTS §6.

Domain types that are also produced by the Quant Engine (``StockMetrics``,
``MarketMetrics``, ``CovarianceMatrix``, ``RiskProfile``, ``FrontierPoint``,
``CALPoint``, ``ORP``, ``CompletePortfolio``, ``OptimizationResult``,
``ReturnFrequency``) are **re-exported from** ``quant.types`` so there is a
single source of truth for those shapes. HTTP-layer-only types (``Quote``,
``PriceBar``, ``HistoricalResponse``, ``RiskFreeRateResponse``,
``OptimizationRequest``, ``ErrorCode``, ``ErrorEnvelope``) live here.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

# Re-export quant domain types so ``app`` and ``quant`` never drift apart.
from quant.types import (
    ORP,
    CALPoint,
    CompletePortfolio,
    CovarianceMatrix,
    FrontierPoint,
    MarketMetrics,
    OptimizationResult,
    ReturnFrequency,
    RiskProfile,
    StockMetrics,
)


class ErrorCode(str, Enum):
    UNKNOWN_TICKER = "UNKNOWN_TICKER"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    DATA_PROVIDER_RATE_LIMIT = "DATA_PROVIDER_RATE_LIMIT"
    DATA_PROVIDER_UNAVAILABLE = "DATA_PROVIDER_UNAVAILABLE"
    OPTIMIZER_INFEASIBLE = "OPTIMIZER_INFEASIBLE"
    OPTIMIZER_NON_PSD_COVARIANCE = "OPTIMIZER_NON_PSD_COVARIANCE"
    INVALID_RISK_PROFILE = "INVALID_RISK_PROFILE"
    INVALID_RETURN_WINDOW = "INVALID_RETURN_WINDOW"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    INTERNAL = "INTERNAL"


class ChatSource(str, Enum):
    RULE = "rule"
    LLM = "llm"


class ChatMode(str, Enum):
    AUTO = "auto"
    RULE = "rule"
    LLM = "llm"


Ticker = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9.]{1,10}$")]


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        ser_json_inf_nan="null",
        extra="forbid",
    )


class PriceBar(_CamelModel):
    date: Date
    open: float
    high: float
    low: float
    close: float
    volume: int


class Quote(_CamelModel):
    ticker: Ticker
    price: float
    as_of: datetime


class HistoricalResponse(_CamelModel):
    ticker: Ticker
    frequency: ReturnFrequency
    bars: list[PriceBar]


class RiskFreeRateResponse(_CamelModel):
    rate: float
    as_of: datetime
    source: Literal["FRED", "FALLBACK"]


class OptimizationRequest(_CamelModel):
    tickers: list[Ticker] = Field(min_length=2, max_length=30)
    risk_profile: RiskProfile
    return_frequency: ReturnFrequency = ReturnFrequency.DAILY
    lookback_years: int = Field(default=5, ge=1, le=20)
    allow_short: bool = True
    allow_leverage: bool = True
    alpha_overrides: dict[Ticker, float] | None = None
    frontier_resolution: int = Field(default=40, ge=5, le=200)


class ChatMessage(_CamelModel):
    role: Literal["user", "assistant"]
    content: str


class ChatCitation(_CamelModel):
    label: str
    value: str


class ChatRequest(_CamelModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    portfolio_context: OptimizationResult | None = None
    mode: ChatMode = ChatMode.AUTO
    session_id: str | None = None
    # OpenRouter model slug selected by the user in the frontend Settings
    # panel. When ``None``, the backend uses the default from ``OPENROUTER_MODEL``.
    # The slug is validated against a safe charset before being forwarded.
    model: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9\-._:/]{0,99}$")] | None = (
        None
    )


class ChatResponse(_CamelModel):
    answer: str
    source: ChatSource
    citations: list[ChatCitation] = Field(default_factory=list)


class ChatHistoryEntry(_CamelModel):
    role: Literal["user", "assistant"]
    content: str
    source: ChatSource | None = None
    citations: list[ChatCitation] = Field(default_factory=list)
    created_at: datetime


class ChatSessionResponse(_CamelModel):
    session_id: str
    portfolio_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatHistoryEntry] = Field(default_factory=list)


class ErrorDetails(_CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        ser_json_inf_nan="null",
        extra="allow",
    )


class ErrorEnvelope(_CamelModel):
    code: ErrorCode
    message: str
    details: dict | None = None


__all__ = [
    "ORP",
    "CALPoint",
    "ChatCitation",
    "ChatHistoryEntry",
    "ChatMessage",
    "ChatMode",
    "ChatRequest",
    "ChatResponse",
    "ChatSessionResponse",
    "ChatSource",
    "CompletePortfolio",
    "CovarianceMatrix",
    "ErrorCode",
    "ErrorDetails",
    "ErrorEnvelope",
    "FrontierPoint",
    "HistoricalResponse",
    "MarketMetrics",
    "OptimizationRequest",
    "OptimizationResult",
    "PriceBar",
    "Quote",
    "ReturnFrequency",
    "RiskFreeRateResponse",
    "RiskProfile",
    "StockMetrics",
    "Ticker",
]
