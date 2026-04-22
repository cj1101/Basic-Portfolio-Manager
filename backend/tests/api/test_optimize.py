"""POST /api/optimize — end-to-end coverage via the stubbed data layer.

These tests cover the integration seam Agent D owns: the FastAPI route
forwards to ``OptimizeService``, which orchestrates the stubbed data
clients (Alpha Vantage + Yahoo + FRED) already configured in
``tests/api/conftest.py`` and the real, pure ``quant`` engine.
"""

from __future__ import annotations

import pytest

from app.errors import RateLimitError, UnknownTickerError

pytestmark = pytest.mark.asyncio


def _basic_body(tickers: list[str] | None = None) -> dict:
    return {
        "tickers": tickers or ["AAPL", "MSFT", "NVDA", "JPM", "XOM"],
        "riskProfile": {"riskAversion": 3, "targetReturn": 0.15},
        "returnFrequency": "daily",
        "lookbackYears": 5,
        "allowShort": True,
        "allowLeverage": True,
        "frontierResolution": 20,
    }


async def test_optimize_happy_path(api_client):
    resp = await api_client.post("/api/optimize", json=_basic_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["requestId"].startswith("opt_")
    assert body["riskFreeRate"] == pytest.approx(0.0462)

    # Top-level shape — every contract field must be present.
    required_keys = {
        "requestId",
        "asOf",
        "riskFreeRate",
        "market",
        "stocks",
        "covariance",
        "correlation",
        "orp",
        "complete",
        "frontierPoints",
        "calPoints",
        "warnings",
    }
    assert required_keys.issubset(body.keys())

    # Market metrics sanity: σ² ≈ σ² (within floating-point slack).
    market = body["market"]
    assert market["variance"] == pytest.approx(market["stdDev"] ** 2, rel=1e-9)

    # Stocks — one per requested ticker, in input order, with CAPM/SIM output
    # shaped as CONTRACTS §3 demands.
    tickers = _basic_body()["tickers"]
    assert [s["ticker"] for s in body["stocks"]] == tickers
    for s in body["stocks"]:
        assert {
            "expectedReturn",
            "stdDev",
            "beta",
            "alpha",
            "firmSpecificVar",
            "nObservations",
        }.issubset(s.keys())
        assert s["nObservations"] > 100
        assert s["stdDev"] > 0
        assert s["firmSpecificVar"] >= 0

    # Covariance symmetry + PSD invariants.
    cov = body["covariance"]["matrix"]
    n = len(cov)
    assert n == len(tickers)
    for i in range(n):
        for j in range(n):
            assert cov[i][j] == pytest.approx(cov[j][i], abs=1e-9)

    # Correlation matrix: labels match, unit diagonal, consistent with Σ.
    corr = body["correlation"]
    assert corr["tickers"] == tickers
    cmat = corr["matrix"]
    assert len(cmat) == n
    for i in range(n):
        for j in range(n):
            assert cmat[i][j] == pytest.approx(cmat[j][i], abs=1e-9)
        assert cmat[i][i] == pytest.approx(1.0, abs=1e-9)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            assert -1.0 - 1e-6 <= cmat[i][j] <= 1.0 + 1e-6
            si = cov[i][i] ** 0.5
            sj = cov[j][j] ** 0.5
            assert cov[i][j] == pytest.approx(si * sj * cmat[i][j], rel=1e-5, abs=1e-9)

    # ORP weights sum to 1 (CONTRACTS §3) and include every input ticker
    # even at 0 (wire-format rule 4 in CONTRACTS §6).
    orp = body["orp"]
    assert set(orp["weights"].keys()) == set(tickers)
    assert sum(orp["weights"].values()) == pytest.approx(1.0, abs=1e-6)
    assert orp["stdDev"] > 0
    assert orp["sharpe"] > 0  # Every mock profile has positive drift.

    # Complete portfolio: y* = (E(r_ORP) − rᶠ) / (A · σ²_ORP), unclamped.
    complete = body["complete"]
    assert set(complete["weights"].keys()) == set(tickers)
    assert complete["yStar"] > 0
    assert complete["weightRiskFree"] == pytest.approx(1.0 - complete["yStar"], abs=1e-9)

    # Frontier / CAL present and sampled to the requested resolution (≤).
    assert len(body["frontierPoints"]) > 5
    assert len(body["calPoints"]) >= 2

    # Provenance headers are set and non-empty.
    assert resp.headers.get("X-Data-Source") in {"alpha-vantage", "yahoo", "mixed"}


async def test_optimize_slider_has_no_network_side_effects(api_client):
    """Changing riskAversion must not change anything except the complete block.

    This is our canary for Agent D's "slider stays client-side" plan: if the
    backend's optimizer ever became risk-aversion-dependent for the ORP, this
    would catch it.
    """
    body_low = _basic_body()
    body_low["riskProfile"]["riskAversion"] = 1
    body_high = _basic_body()
    body_high["riskProfile"]["riskAversion"] = 8

    resp_low = await api_client.post("/api/optimize", json=body_low)
    resp_high = await api_client.post("/api/optimize", json=body_high)

    assert resp_low.status_code == resp_high.status_code == 200
    low, high = resp_low.json(), resp_high.json()

    assert low["orp"]["weights"] == high["orp"]["weights"]
    assert low["orp"]["expectedReturn"] == pytest.approx(high["orp"]["expectedReturn"])
    # Complete portfolio DOES shift with risk aversion (higher A ⇒ lower y*).
    assert high["complete"]["yStar"] < low["complete"]["yStar"]


async def test_optimize_rejects_single_ticker(api_client):
    body = _basic_body(tickers=["AAPL"])
    resp = await api_client.post("/api/optimize", json=body)
    assert resp.status_code == 400
    assert resp.json()["code"] in {"INVALID_RETURN_WINDOW"}


async def test_optimize_rejects_spy_as_holding(api_client):
    body = _basic_body(tickers=["AAPL", "SPY"])
    resp = await api_client.post("/api/optimize", json=body)
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "INVALID_RETURN_WINDOW"
    assert "SPY" in body["message"] or body.get("details", {}).get("ticker") == "SPY"


async def test_optimize_rejects_invalid_risk_profile(api_client):
    body = _basic_body()
    body["riskProfile"]["riskAversion"] = 42
    resp = await api_client.post("/api/optimize", json=body)
    assert resp.status_code == 400


async def test_optimize_unknown_ticker(api_client, api_state):
    """An unknown ticker from BOTH providers surfaces as 404 UNKNOWN_TICKER."""

    class _FailingYahoo:
        async def get_historical_daily(self, ticker, **kwargs):
            raise UnknownTickerError(ticker)

        async def get_quote(self, ticker):
            raise UnknownTickerError(ticker)

        async def close(self):
            return None

    orig_av = api_state.alpha_vantage
    real_get = orig_av.get_historical_daily

    async def _av_unknown_for_fake(ticker: str, **kwargs):
        if ticker == "FAKETICKER":
            raise UnknownTickerError(ticker)
        return await real_get(ticker, **kwargs)

    orig_av.get_historical_daily = _av_unknown_for_fake  # type: ignore[assignment]
    api_state.service._yahoo = _FailingYahoo()

    body = _basic_body(tickers=["AAPL", "FAKETICKER"])
    resp = await api_client.post("/api/optimize", json=body)

    assert resp.status_code == 404
    assert resp.json()["code"] == "UNKNOWN_TICKER"


async def test_optimize_rate_limit_preserves_429(api_client, api_state):
    """When every provider is rate-limited we must return 429, not 503."""
    orig_av = api_state.alpha_vantage
    orig_av.hist_exc = RateLimitError("alpha-vantage", 30.0, scope="day")

    class _RateLimitedYahoo:
        async def get_historical_daily(self, ticker, **kwargs):
            raise RateLimitError("yahoo", 15.0, scope="minute")

        async def get_quote(self, ticker):
            raise RateLimitError("yahoo", 15.0, scope="minute")

        async def close(self):
            return None

    api_state.service._yahoo = _RateLimitedYahoo()

    resp = await api_client.post("/api/optimize", json=_basic_body(tickers=["AAPL", "MSFT"]))
    assert resp.status_code == 429
    assert resp.json()["code"] == "DATA_PROVIDER_RATE_LIMIT"
    assert resp.headers.get("Retry-After") is not None


async def test_optimize_validation_error_too_many_tickers(api_client):
    body = _basic_body(tickers=[f"T{i:02d}" for i in range(35)])
    resp = await api_client.post("/api/optimize", json=body)
    assert resp.status_code == 400
