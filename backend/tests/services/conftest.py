"""Shared fixtures for the chat-service test suite (Agent E).

Provides a small hand-built :class:`OptimizationResult` so the rule engine
and the LLM client can be exercised without running the full Agent D
pipeline. Numbers are illustrative — only structure / shape / wire-format
need to be valid for these tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from app.schemas import (
    ORP,
    CALPoint,
    CompletePortfolio,
    CorrelationMatrix,
    CovarianceMatrix,
    FrontierPoint,
    MarketMetrics,
    OptimizationResult,
    StockMetrics,
)
from quant.linalg import covariance_to_correlation


@pytest.fixture
def sample_optimization_result() -> OptimizationResult:
    tickers = ["AAPL", "MSFT", "NVDA"]
    return OptimizationResult(
        request_id="opt_test_0001",
        as_of=datetime(2025, 4, 1, tzinfo=UTC),
        risk_free_rate=0.0523,
        market=MarketMetrics(
            expected_return=0.105,
            std_dev=0.185,
            variance=0.034225,
        ),
        stocks=[
            StockMetrics(
                ticker="AAPL",
                expected_return=0.21,
                std_dev=0.27,
                beta=1.22,
                alpha=0.041,
                firm_specific_var=0.034,
                n_observations=1258,
            ),
            StockMetrics(
                ticker="MSFT",
                expected_return=0.19,
                std_dev=0.24,
                beta=1.08,
                alpha=0.028,
                firm_specific_var=0.029,
                n_observations=1258,
            ),
            StockMetrics(
                ticker="NVDA",
                expected_return=0.44,
                std_dev=0.41,
                beta=1.63,
                alpha=0.22,
                firm_specific_var=0.091,
                n_observations=1258,
            ),
        ],
        covariance=CovarianceMatrix(
            tickers=list(tickers),
            matrix=[
                [0.0729, 0.054, 0.061],
                [0.054, 0.0576, 0.0432],
                [0.061, 0.0432, 0.1681],
            ],
        ),
        correlation=CorrelationMatrix(
            tickers=list(tickers),
            matrix=covariance_to_correlation(
                np.array(
                    [
                        [0.0729, 0.054, 0.061],
                        [0.054, 0.0576, 0.0432],
                        [0.061, 0.0432, 0.1681],
                    ],
                    dtype=np.float64,
                )
            ).tolist(),
        ),
        orp=ORP(
            weights={"AAPL": 0.28, "MSFT": 0.22, "NVDA": 0.50},
            expected_return=0.29,
            std_dev=0.31,
            variance=0.0961,
            sharpe=0.767,
        ),
        complete=CompletePortfolio(
            y_star=0.95,
            weight_risk_free=0.05,
            weights={"AAPL": 0.266, "MSFT": 0.209, "NVDA": 0.475},
            expected_return=0.276,
            std_dev=0.2945,
            leverage_used=False,
        ),
        frontier_points=[
            FrontierPoint(std_dev=0.16, expected_return=0.12),
            FrontierPoint(std_dev=0.21, expected_return=0.20),
            FrontierPoint(std_dev=0.31, expected_return=0.29),
        ],
        cal_points=[
            CALPoint(std_dev=0.0, expected_return=0.0523, y=0.0),
            CALPoint(std_dev=0.31, expected_return=0.29, y=1.0),
        ],
        warnings=[],
    )
