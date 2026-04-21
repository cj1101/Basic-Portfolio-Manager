"""Pydantic models for the Quant Engine.

These mirror the TypeScript types in ``docs/CONTRACTS.md`` §3 field-for-field.
The wire format is always ``camelCase``; Python code accesses ``snake_case``
via Pydantic's ``alias_generator``. ``populate_by_name=True`` lets internal
code build models from snake_case kwargs while JSON round-trips through the
camelCase aliases.

This module is deliberately narrow: only the types the Quant Engine produces
live here (stocks, market, ORP, complete portfolio, frontier, CAL, optimization
result). Data-layer types (``PriceBar``, ``Quote``) belong to Agent 1A Data.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

Ticker = str


class ReturnFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


_WIRE_CONFIG = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
    ser_json_inf_nan="null",
    frozen=False,
    extra="forbid",
)


class _WireModel(BaseModel):
    """Base model with camelCase wire format and strict extras."""

    model_config = _WIRE_CONFIG


class StockMetrics(_WireModel):
    ticker: Ticker
    expected_return: float
    std_dev: float
    beta: float
    alpha: float
    firm_specific_var: float
    n_observations: int = Field(ge=0)


class MarketMetrics(_WireModel):
    expected_return: float
    std_dev: float
    variance: float


class CovarianceMatrix(_WireModel):
    tickers: list[Ticker]
    matrix: list[list[float]]

    @field_validator("matrix")
    @classmethod
    def _square_and_matching(cls, v: list[list[float]], info: Any) -> list[list[float]]:
        tickers = info.data.get("tickers")
        if tickers is None:
            return v
        n = len(tickers)
        if len(v) != n:
            raise ValueError(f"matrix must have {n} rows, got {len(v)}")
        for row in v:
            if len(row) != n:
                raise ValueError(f"each row must have {n} columns, got {len(row)}")
        return v


class RiskProfile(_WireModel):
    risk_aversion: int = Field(ge=1, le=10)
    target_return: float | None = None


class FrontierPoint(_WireModel):
    std_dev: float
    expected_return: float


class CALPoint(_WireModel):
    std_dev: float
    expected_return: float
    y: float


class ORP(_WireModel):
    weights: dict[Ticker, float]
    expected_return: float
    std_dev: float
    variance: float
    sharpe: float


class CompletePortfolio(_WireModel):
    y_star: float
    weight_risk_free: float
    weights: dict[Ticker, float]
    expected_return: float
    std_dev: float
    leverage_used: bool


class OptimizationResult(_WireModel):
    request_id: str
    as_of: datetime
    risk_free_rate: float
    market: MarketMetrics
    stocks: list[StockMetrics]
    covariance: CovarianceMatrix
    orp: ORP
    complete: CompletePortfolio
    frontier_points: list[FrontierPoint]
    cal_points: list[CALPoint]
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "ORP",
    "CALPoint",
    "CompletePortfolio",
    "CovarianceMatrix",
    "FrontierPoint",
    "MarketMetrics",
    "OptimizationResult",
    "ReturnFrequency",
    "RiskProfile",
    "StockMetrics",
    "Ticker",
]
