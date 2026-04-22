"""Wire-format types — mirrors docs/CONTRACTS.md §2–§4 field-for-field.

All models serialize to camelCase JSON via ``alias_generator=to_camel``. Python
code always reads the snake_case attribute; the wire format is the camelCase
alias. Non-finite floats are rejected at serialization time per CONTRACTS §6.

Domain types that are also produced by the Quant Engine (``StockMetrics``,
``MarketMetrics``, ``CovarianceMatrix``, ``CorrelationMatrix``, ``RiskProfile``, ``FrontierPoint``,
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
    CorrelationMatrix,
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
    INVALID_VALUATION = "INVALID_VALUATION"
    INVALID_SETTINGS = "INVALID_SETTINGS"
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


# --- analytics / valuation (CONTRACTS §3 / §5.13–5.14) ---


class HoldingPeriodMonthlyReturns(_CamelModel):
    years: int
    n_observations: int
    window_start: Date
    window_end: Date
    arithmetic_mean_monthly_return: float
    geometric_mean_monthly_return: float


class ORPPerformanceMetrics(_CamelModel):
    treynor: float
    jensen_alpha: float
    n_observations: int
    total_variance: float
    systematic_variance: float
    unsystematic_variance: float
    sim_variance_mismatch: float


class CompletePerformanceMetrics(_CamelModel):
    treynor: float
    jensen_alpha: float
    n_observations: int
    total_variance: float
    systematic_variance: float
    unsystematic_variance: float
    sim_variance_mismatch: float


class FamaFrenchThreePerTicker(_CamelModel):
    ticker: Ticker
    beta_mkt: float
    beta_smb: float
    beta_hml: float
    alpha: float
    n_observations: int
    expected_return_ff3: float
    expected_return_capm: float


class AnalyticsPerformanceRequest(_CamelModel):
    tickers: list[Ticker] = Field(min_length=2, max_length=30)
    orp_weights: dict[Ticker, float]
    return_frequency: ReturnFrequency = ReturnFrequency.DAILY
    lookback_years: int = Field(default=5, ge=1, le=20)
    y_star: float | None = None
    weight_risk_free: float | None = None


class AnalyticsPerformanceResult(_CamelModel):
    as_of: datetime
    window_start: Date
    window_end: Date
    risk_free_rate: float
    data_source: str
    orp: ORPPerformanceMetrics
    complete: CompletePerformanceMetrics | None = None
    holding: list[HoldingPeriodMonthlyReturns]
    fama_french: list[FamaFrenchThreePerTicker]
    market: MarketMetrics
    warnings: list[str] = Field(default_factory=list)


class DdmTwoStageParams(_CamelModel):
    g1: float
    g2: float
    n_periods: int = Field(ge=1, le=200)


class ValuationRequest(_CamelModel):
    tickers: list[Ticker] = Field(min_length=1, max_length=20)
    wacc: float | None = None
    fcff_growth: float | None = None
    fcff_terminal_growth: float | None = None
    cost_of_equity_override: float | None = None
    ddm_gordon_g: float | None = None
    ddm_two_stage: DdmTwoStageParams | None = None


class TickerValuationBlock(_CamelModel):
    ticker: Ticker
    fcff: float | None
    fcfe: float | None
    fcff_value_per_share: float | None
    fcfe_value_per_share: float | None
    ddm_gordon: float | None
    ddm_two_stage: float | None
    cost_of_equity: float
    warnings: list[str] = Field(default_factory=list)


class ValuationResult(_CamelModel):
    as_of: datetime
    per_ticker: list[TickerValuationBlock]
    data_source: str
    warnings: list[str] = Field(default_factory=list)


ApiKeyName = Literal["OPENROUTER_API_KEY", "ALPHA_VANTAGE_API_KEY", "FRED_API_KEY"]


class UpdateApiKeyRequest(_CamelModel):
    key_name: ApiKeyName
    new_value: str
    confirm_overwrite: bool = False
    confirm_create: bool = False


class UpdateApiKeyResponse(_CamelModel):
    updated: bool
    created: bool
    restart_required: bool
    requires_confirmation: bool
    confirmation_type: Literal["overwrite", "create"] | None = None
    message: str


__all__ = [
    "AnalyticsPerformanceRequest",
    "AnalyticsPerformanceResult",
    "CompletePerformanceMetrics",
    "DdmTwoStageParams",
    "FamaFrenchThreePerTicker",
    "HoldingPeriodMonthlyReturns",
    "ORP",
    "ORPPerformanceMetrics",
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
    "CorrelationMatrix",
    "CovarianceMatrix",
    "ErrorCode",
    "ErrorDetails",
    "ErrorEnvelope",
    "FrontierPoint",
    "HistoricalResponse",
    "ApiKeyName",
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
    "TickerValuationBlock",
    "UpdateApiKeyRequest",
    "UpdateApiKeyResponse",
    "ValuationRequest",
    "ValuationResult",
]
