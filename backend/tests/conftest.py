"""Shared pytest fixtures.

This conftest is deliberately shared between Agent 1A (data layer) and
Agent 1C (quant engine). The data-layer fixtures (``cache``, ``rate_limiter``,
``isolated_settings``…) live alongside the Dataset A / CAPM fixtures the
quant tests consume. Keeping them in one place avoids Agent 1A and Agent 1C
clobbering each other's ``conftest.py`` every merge.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio
from numpy.typing import NDArray

from app.data.cache import MarketCache
from app.data.rate_limit import AlphaVantageRateLimiter
from app.settings import Settings, override_settings, reset_settings


# ---------------------------------------------------------------------------
# Data-layer fixtures (Agent 1A)
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(config, items):
    run_live = os.getenv("RUN_LIVE_TESTS") == "1"
    if run_live:
        return
    skip_live = pytest.mark.skip(reason="live tests require RUN_LIVE_TESTS=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture
def load_fixture(fixture_dir: Path):
    def _load(name: str) -> dict:
        path = fixture_dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch) -> Iterator[Settings]:
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setenv("FRED_API_KEY", "fred-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CACHE_DB_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setenv("USE_MOCK_FALLBACK", "false")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    reset_settings()
    settings = Settings()
    override_settings(settings)
    try:
        yield settings
    finally:
        reset_settings()


@pytest_asyncio.fixture
async def cache(isolated_settings: Settings) -> AsyncIterator[MarketCache]:
    c = MarketCache(isolated_settings.cache_db_path)
    await c.connect()
    try:
        yield c
    finally:
        await c.close()


@pytest_asyncio.fixture
async def rate_limiter(cache: MarketCache) -> AlphaVantageRateLimiter:
    return AlphaVantageRateLimiter(cache, per_minute=5, per_day=500, minute_window=60.0)


# ---------------------------------------------------------------------------
# Quant-engine fixtures (Agent 1C — Dataset A per docs/FIXTURES.md §1)
# ---------------------------------------------------------------------------

TOLERANCE_SCALAR: float = 1e-6
TOLERANCE_WEIGHT_SUM: float = 1e-9
TOLERANCE_SYMMETRY: float = 1e-10
TOLERANCE_PSD: float = 1e-8


@dataclass(frozen=True)
class DatasetAFixture:
    tickers: tuple[str, ...]
    risk_free_rate: float
    expected_returns: NDArray[np.float64]
    std_devs: NDArray[np.float64]
    correlation: NDArray[np.float64]
    covariance: NDArray[np.float64]
    orp_weights: dict[str, float]
    orp_expected_return: float
    orp_std_dev: float
    orp_variance: float
    orp_sharpe: float
    mvp_weights: dict[str, float]
    mvp_expected_return: float
    mvp_std_dev: float
    mvp_variance: float


@dataclass(frozen=True)
class DatasetACAPMFixture:
    risk_free_rate: float
    market_expected_return: float
    market_std_dev: float
    market_variance: float
    beta: float
    alpha: float
    firm_specific_var: float
    required_return: float
    total_expected_return: float
    systematic_variance: float
    total_variance: float
    std_dev: float


@pytest.fixture(scope="session")
def dataset_a() -> DatasetAFixture:
    """Dataset A — synthetic textbook inputs & closed-form expected outputs."""

    tickers = ("S1", "S2", "S3")
    rf = 0.04
    mu = np.asarray([0.10, 0.13, 0.16], dtype=np.float64)
    sigma = np.asarray([0.15, 0.20, 0.30], dtype=np.float64)
    rho = np.eye(3, dtype=np.float64)
    cov = np.diag(sigma**2)

    orp = {"S1": 32.0 / 75.0, "S2": 9.0 / 25.0, "S3": 16.0 / 75.0}
    orp_e_r = 0.1236
    orp_var = 0.013376
    orp_sd = float(np.sqrt(orp_var))
    orp_sharpe = (orp_e_r - rf) / orp_sd

    mvp = {"S1": 16.0 / 29.0, "S2": 9.0 / 29.0, "S3": 4.0 / 29.0}
    mvp_e_r = 3.41 / 29.0
    mvp_var = 10.44 / 841.0
    mvp_sd = float(np.sqrt(mvp_var))

    return DatasetAFixture(
        tickers=tickers,
        risk_free_rate=rf,
        expected_returns=mu,
        std_devs=sigma,
        correlation=rho,
        covariance=cov,
        orp_weights=orp,
        orp_expected_return=orp_e_r,
        orp_std_dev=orp_sd,
        orp_variance=orp_var,
        orp_sharpe=orp_sharpe,
        mvp_weights=mvp,
        mvp_expected_return=mvp_e_r,
        mvp_std_dev=mvp_sd,
        mvp_variance=mvp_var,
    )


@pytest.fixture(scope="session")
def dataset_a_capm() -> DatasetACAPMFixture:
    """Dataset A single-stock CAPM/SIM test (``docs/FIXTURES.md`` §1)."""

    rf = 0.04
    market_e_r = 0.10
    market_sd = 0.18
    market_var = market_sd**2
    beta = 1.2
    alpha = 0.02
    firm = 0.01

    required = 0.112
    total_e_r = 0.132
    sys_var = beta * beta * market_var
    total_var = sys_var + firm
    sd = float(np.sqrt(total_var))

    return DatasetACAPMFixture(
        risk_free_rate=rf,
        market_expected_return=market_e_r,
        market_std_dev=market_sd,
        market_variance=market_var,
        beta=beta,
        alpha=alpha,
        firm_specific_var=firm,
        required_return=required,
        total_expected_return=total_e_r,
        systematic_variance=sys_var,
        total_variance=total_var,
        std_dev=sd,
    )
