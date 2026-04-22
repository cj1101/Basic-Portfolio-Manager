"""Unit tests for ``app.services.optimize_service.OptimizeService``.

These tests exercise the orchestrator directly (bypassing HTTP) against a
stubbed ``DataService`` — that way the math gets hit end-to-end with full
control over the bar stream and the risk-free rate.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pytest

from app.data.service import HistoricalResult, RiskFreeRateResult
from app.errors import InsufficientHistoryError, InvalidReturnWindowError
from app.schemas import OptimizationRequest, PriceBar, ReturnFrequency, RiskProfile
from app.services import MARKET_PROXY_TICKER, OptimizeService
from app.services.optimize_service import _normalize_request_tickers
from app.services.returns_frame import build_return_frame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bars_from_returns(
    returns: np.ndarray,
    *,
    start_price: float = 100.0,
    end_date: Date = Date(2024, 11, 21),
) -> list[PriceBar]:
    """Build a deterministic ``PriceBar`` list from per-period returns.

    Closes follow a pure log-linear path so ``log(close_t/close_{t-1}) == r_t``.
    OHLV fields are filled with placeholder values; the optimize service only
    reads ``close``.
    """
    closes = start_price * np.exp(np.cumsum(np.concatenate([[0.0], returns])))
    n = closes.shape[0]
    dates = [end_date - timedelta(days=(n - 1 - i)) for i in range(n)]
    return [
        PriceBar(
            date=dates[i],
            open=float(closes[i]),
            high=float(closes[i]),
            low=float(closes[i]),
            close=float(closes[i]),
            volume=1_000_000,
        )
        for i in range(n)
    ]


class StubDataService:
    """Minimal quacks-like-:class:`DataService` for the orchestrator tests."""

    def __init__(
        self,
        *,
        bars_by_ticker: dict[str, list[PriceBar]],
        risk_free_rate: float = 0.04,
        historical_source: str = "alpha-vantage",
        rfr_source: str = "FRED",
        historical_warnings: dict[str, list[str]] | None = None,
        rfr_warnings: list[str] | None = None,
    ) -> None:
        self._bars = bars_by_ticker
        self._rf = risk_free_rate
        self._historical_source = historical_source
        self._rfr_source = rfr_source
        self._historical_warnings = historical_warnings or {}
        self._rfr_warnings = rfr_warnings or []
        self.historical_calls: list[tuple[str, ReturnFrequency, int]] = []
        self.rfr_calls: int = 0

    async def get_historical(
        self,
        ticker: str,
        *,
        frequency: ReturnFrequency,
        lookback_years: int,
        as_of: Any = None,
    ) -> HistoricalResult:
        self.historical_calls.append((ticker, frequency, lookback_years))
        if ticker not in self._bars:
            from app.errors import UnknownTickerError

            raise UnknownTickerError(ticker)
        return HistoricalResult(
            ticker=ticker,
            frequency=frequency,
            bars=self._bars[ticker],
            source=self._historical_source,
            warnings=list(self._historical_warnings.get(ticker, [])),
        )

    async def get_risk_free_rate(self) -> RiskFreeRateResult:
        self.rfr_calls += 1
        return RiskFreeRateResult(
            rate=self._rf,
            as_of=datetime(2024, 11, 20, tzinfo=timezone.utc),
            source=self._rfr_source,
            warnings=list(self._rfr_warnings),
        )


def _synthetic_universe(
    tickers: list[str],
    *,
    n: int = 1000,
    seed: int = 7,
) -> dict[str, list[PriceBar]]:
    """Build n+1 price bars for each ticker + SPY from deterministic GBM."""
    rng = np.random.default_rng(seed)
    mkt = rng.normal(loc=0.0006, scale=0.01, size=n)
    bars: dict[str, list[PriceBar]] = {}
    # Generous drifts (annualized ~0.20–0.35) ensure the ORP's excess return is
    # comfortably positive so y* > 0 regardless of any short-exposure that the
    # unconstrained tangency formula takes in the universe.
    profiles = {
        "AAA": (0.0012, 0.012, 1.1),
        "BBB": (0.0010, 0.014, 0.9),
        "CCC": (0.0009, 0.018, 1.3),
        "DDD": (0.0008, 0.010, 0.6),
    }
    for t in tickers:
        drift, vol, beta = profiles.get(t, (0.0004, 0.012, 1.0))
        idio = rng.normal(loc=0.0, scale=vol, size=n)
        rets = drift + beta * mkt + idio
        bars[t] = _bars_from_returns(rets)
    bars[MARKET_PROXY_TICKER] = _bars_from_returns(mkt)
    return bars


# ---------------------------------------------------------------------------
# Ticker normalization
# ---------------------------------------------------------------------------


def test_normalize_request_tickers_dedupes_and_uppercases():
    assert _normalize_request_tickers([" aapl ", "MSFT", "aapl"]) == ("AAPL", "MSFT")


def test_normalize_request_tickers_rejects_spy_holding():
    with pytest.raises(InvalidReturnWindowError):
        _normalize_request_tickers(["AAPL", "SPY"])


def test_normalize_request_tickers_rejects_under_two():
    with pytest.raises(InvalidReturnWindowError):
        _normalize_request_tickers(["AAPL"])


# ---------------------------------------------------------------------------
# Return-frame builder
# ---------------------------------------------------------------------------


def test_build_return_frame_inner_joins_shared_dates():
    base = Date(2024, 1, 15)
    bars_a = [
        PriceBar(date=base - timedelta(days=i), open=100, high=100, low=100, close=100 * (1 + 0.001 * i), volume=1)
        for i in range(10)
    ]
    bars_b = [
        # B is only 5 long; join should trim A to B's latest 5 shared dates.
        PriceBar(date=base - timedelta(days=i), open=100, high=100, low=100, close=100 * (1 + 0.002 * i), volume=1)
        for i in range(5)
    ]
    frame = build_return_frame({"A": bars_a, "B": bars_b}, column_order=("A", "B"))
    assert frame.shape[1] == 2
    # Log-diffs across 5 shared observations ⇒ 4 rows.
    assert frame.shape[0] == 4
    assert list(frame.columns) == ["A", "B"]


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


async def test_run_happy_path_produces_valid_result():
    tickers = ["AAA", "BBB", "CCC"]
    bars = _synthetic_universe(tickers)
    stub = StubDataService(bars_by_ticker=bars, risk_free_rate=0.04)

    service = OptimizeService()
    request = OptimizationRequest(
        tickers=tickers,
        risk_profile=RiskProfile(risk_aversion=3, target_return=None),
        return_frequency=ReturnFrequency.DAILY,
        lookback_years=5,
        allow_short=True,
        allow_leverage=True,
        frontier_resolution=40,
    )

    result = await service.run(request, data_service=stub)

    assert stub.rfr_calls == 1
    # SPY pulled in automatically as the market proxy — 3 tickers + 1 SPY.
    fetched = {t for (t, _, _) in stub.historical_calls}
    assert fetched == {*tickers, MARKET_PROXY_TICKER}

    assert result.provenance.source == "alpha-vantage"
    assert result.provenance.per_ticker_sources[MARKET_PROXY_TICKER] == "alpha-vantage"

    wire = result.result

    # Invariants (CONTRACTS §3):
    # - every requested ticker appears in stocks, ORP.weights, complete.weights
    assert [s.ticker for s in wire.stocks] == tickers
    assert set(wire.orp.weights.keys()) == set(tickers)
    assert set(wire.complete.weights.keys()) == set(tickers)
    # - ORP weights sum to 1
    assert sum(wire.orp.weights.values()) == pytest.approx(1.0, abs=1e-9)
    # - std_dev² == variance for ORP
    assert wire.orp.variance == pytest.approx(wire.orp.std_dev ** 2, rel=1e-9)
    # - Complete ER = rf + y* · (E(r_ORP) − rf)
    expected_complete_er = (
        wire.risk_free_rate + wire.complete.y_star * (wire.orp.expected_return - wire.risk_free_rate)
    )
    assert wire.complete.expected_return == pytest.approx(expected_complete_er, abs=1e-9)
    # - CAL passes through (0, rf)
    first_cal = wire.cal_points[0]
    assert first_cal.std_dev == pytest.approx(0.0, abs=1e-12)
    assert first_cal.expected_return == pytest.approx(wire.risk_free_rate, abs=1e-12)
    # - covariance is symmetric
    n = len(tickers)
    for i in range(n):
        for j in range(n):
            assert wire.covariance.matrix[i][j] == pytest.approx(
                wire.covariance.matrix[j][i], abs=1e-9
            )


async def test_run_propagates_data_warnings():
    tickers = ["AAA", "BBB", "CCC"]
    bars = _synthetic_universe(tickers)
    stub = StubDataService(
        bars_by_ticker=bars,
        historical_warnings={"AAA": ["Alpha Vantage rate-limited; used Yahoo fallback"]},
        rfr_warnings=["FRED unavailable: demo; using static fallback"],
    )

    request = OptimizationRequest(
        tickers=tickers,
        risk_profile=RiskProfile(risk_aversion=3, target_return=None),
        frontier_resolution=20,
    )
    result = await OptimizeService().run(request, data_service=stub)

    joined = " | ".join(result.result.warnings)
    assert "FRED unavailable" in joined
    assert "AAA: Alpha Vantage rate-limited" in joined


async def test_run_rejects_short_history():
    # Short window — 10 daily bars per ticker, < 30 aligned observations.
    def _short_bars() -> list[PriceBar]:
        end = Date(2024, 11, 21)
        return [
            PriceBar(
                date=end - timedelta(days=i),
                open=100,
                high=100,
                low=100,
                close=100 * (1 + 0.001 * i),
                volume=1,
            )
            for i in range(10)
        ]

    stub = StubDataService(
        bars_by_ticker={"AAA": _short_bars(), "BBB": _short_bars(), MARKET_PROXY_TICKER: _short_bars()}
    )
    request = OptimizationRequest(
        tickers=["AAA", "BBB"],
        risk_profile=RiskProfile(risk_aversion=3),
    )
    with pytest.raises(InsufficientHistoryError):
        await OptimizeService().run(request, data_service=stub)


async def test_run_aggregates_provenance_across_providers():
    tickers = ["AAA", "BBB"]
    bars = _synthetic_universe(tickers)

    # Simulate AAA from Alpha Vantage, BBB from Yahoo, SPY from Alpha Vantage.
    class MixedStub(StubDataService):
        async def get_historical(self, ticker, *, frequency, lookback_years, as_of=None):
            res = await super().get_historical(
                ticker, frequency=frequency, lookback_years=lookback_years, as_of=as_of
            )
            if ticker == "BBB":
                res.source = "yahoo"
            return res

    stub = MixedStub(bars_by_ticker=bars)
    request = OptimizationRequest(
        tickers=tickers,
        risk_profile=RiskProfile(risk_aversion=3),
        frontier_resolution=20,
    )
    result = await OptimizeService().run(request, data_service=stub)
    assert result.provenance.source == "mixed"
    assert result.provenance.per_ticker_sources["AAA"] == "alpha-vantage"
    assert result.provenance.per_ticker_sources["BBB"] == "yahoo"
