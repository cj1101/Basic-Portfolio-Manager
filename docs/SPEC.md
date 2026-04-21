# Portfolio Manager — Product Specification (SPEC.md)

> **This is a Phase 0 artifact.** It is the single source of truth for product decisions. Every downstream agent (Phase 1+) MUST read this file, [CONTRACTS.md](CONTRACTS.md), [FIXTURES.md](FIXTURES.md), and [../.cursor/rules/quant.mdc](../.cursor/rules/quant.mdc) before writing any code. If reality forces a change to any decision below, update SPEC.md first and notify all active agents — never drift silently.

---

## 1. Mission

Build a transparent, ticker-driven portfolio manager that turns a list of stocks plus a client risk profile into a mathematically optimal allocation along the Capital Allocation Line. The app exposes every step of the decision pipeline (efficient frontier → CAPM/alpha discovery → personalized asset allocation) through an interactive React dashboard, and lets the user interrogate the result via a chat box. The math must be numerically correct first, visually polished second.

---

## 2. Personas & primary journey

**Primary persona — "Alex," a self-directed retail investor** who understands the vocabulary (Sharpe, beta, alpha, T-bills) and wants to see the underlying math, not a black box.

**Primary journey (happy path):**

1. Alex lands on the dashboard, enters 3–20 tickers (e.g. `AAPL, MSFT, NVDA, JPM, XOM`).
2. Alex either drags a risk-aversion slider (`A = 1..10`) or takes the short questionnaire which maps to the same `A`.
3. Alex optionally enters a target annualized return (e.g. `0.15`).
4. The app fetches historical prices (Alpha Vantage, cached), computes per-stock metrics and the covariance matrix, runs the Markowitz optimizer (with shorts + leverage permitted), and produces an `OptimizationResult` in < 5 s after cache warm-up.
5. Alex navigates five tabs (Overview, Efficient Frontier, CAPM/Alpha, Asset Allocation, APIs & Data) to inspect the result.
6. Alex asks the chat box "Why is NVDA overweight?" and gets a grounded, portfolio-aware answer.
7. Alex saves the portfolio, optionally exports a PDF, and later returns to compare drift and rebalance.

---

## 3. Locked product decisions

These were captured in the Phase 0 Q&A and are frozen for the rest of the build. Changing any of them requires updating this section and [CONTRACTS.md](CONTRACTS.md) together.

| # | Decision | Value |
|---|---|---|
| 1 | Tech stack | **Vite + React 18 + TypeScript** frontend, **FastAPI (Python 3.11+)** backend. Math in `numpy`, `scipy`, `cvxpy`. |
| 2 | Stock input | Ticker-driven. User types ticker symbols; app fetches live historical prices and auto-computes all metrics. No manual-entry mode in v1. |
| 3 | Optimizer constraints | **Full MPT** — short positions (negative weights) permitted; leverage (sum of risky weights > 1 via the CAL) permitted. The UI must communicate both clearly. |
| 4 | Market data API | **Alpha Vantage** (`ALPHA_VANTAGE_API_KEY`, free tier: 5 requests/minute, 500/day) is the primary provider. **Yahoo Finance** (via `yfinance`, no key) is an automatic fallback when AV is rate-limited, returns a soft-limit note, or is otherwise unavailable. A **deterministic GBM mock** is an opt-in last-resort fallback (`USE_MOCK_FALLBACK=1`) so demos stay green with no network. Every response carries `X-Data-Source: ALPHA_VANTAGE \| YAHOO \| MOCK \| CACHE \| FALLBACK` so the UI can show provenance. FRED (`DGS3MO`) for risk-free rate with a constant fallback if `FRED_API_KEY` is unset. |
| 5 | Chat box | **Hybrid** — rule-based intent classifier + templated answers over live portfolio state by default. Optional LLM fallback (OpenAI) when `OPENAI_API_KEY` is set; response carries `source: "rule" \| "llm"`. |
| 6 | Risk-aversion capture | **Both** — slider (`A ∈ [1,10]`, default `A=3`) is primary; optional questionnaire mode writes into the same scalar `A`. |
| 7 | Return-estimation convention | **Configurable** via request: default is **daily log-returns**, **5-year lookback**, annualized by ×252 for `E(r)` and ×√252 for `σ`. Monthly + custom windows supported. |
| 8 | Alpha source | **Historical regression residual**: `αᵢ = mean(excess_i) − βᵢ · mean(excess_market)` computed over the same return window. Documented in UI copy as *backward-looking*. |
| 9 | v1 scope | **Full** — optimizer + 5 tabs + chat + backtest + saved portfolios + rebalancing drift + multi-portfolio compare + PDF export. |

---

## 4. In-scope features (mapped to endpoints)

| Feature | Endpoint(s) | Owner agent (Phase 1+) |
|---|---|---|
| Fetch quote for a ticker | `GET /quote` | 1A Data |
| Fetch historical bars | `GET /historical` | 1A Data |
| Current risk-free rate | `GET /risk-free-rate` | 1A Data |
| Compute metrics + run optimizer | `POST /optimize` | 2A Integration (uses 1A + 1C) |
| Backtest the optimizer over history | `POST /backtest` | 3B Backtest |
| Saved portfolios (CRUD) | `GET/POST/PUT/DELETE /portfolios` | 3C Multi-portfolio |
| Rebalancing drift report | `POST /portfolios/{id}/drift` | 3C Multi-portfolio |
| Side-by-side portfolio compare | `POST /compare` | 3C Multi-portfolio |
| Chat over current portfolio | `POST /chat` | 3A Chatbot |
| Export result to PDF | `POST /export/pdf` | 4 Polish |

All shapes are nailed down in [CONTRACTS.md](CONTRACTS.md).

---

## 5. Out-of-scope for v1 (protects against Phase 3 scope creep)

These are explicitly **NOT** being built. If a downstream agent starts sliding toward one, stop and escalate.

- Real trading / broker API integration (Alpaca, IBKR, etc.). This is read-only analytics.
- Options, futures, crypto, fixed-income, FX. Equities only.
- Factor models beyond the Single-Index Model (no Fama-French, no Black-Litterman).
- Tax-lot optimization / tax-loss harvesting.
- Multi-currency / FX-adjusted returns. USD only.
- User authentication / multi-tenant. Local single-user by default; auth is a Phase 5+ concern.
- Intraday data. Daily bars only.
- Mobile-specific UI. Desktop-first; responsive is nice-to-have.

---

## 6. Non-functional requirements

### Rate limiting & caching

- **Alpha Vantage**: 5 req/min, 500 req/day, enforced by a token-bucket rate limiter in `backend/app/data/clients/alpha_vantage.py` (per-minute bucket in memory; per-day counter persisted in SQLite so it survives restarts). Never call AV from any other module.
- **Cache**: SQLite at `backend/.cache/market.db`. Historical daily bars cached indefinitely (immutable); latest-price quotes cached 5 minutes; risk-free rate cached 24 hours. Weekly/monthly frequencies are resampled from the cached daily bars, never re-fetched.
- **Request coalescing**: parallel requests for the same `(ticker, frequency, window)` share a single in-flight fetch via `MarketCache.singleflight` (prevents burning the quota on duplicate concurrent calls).

### Provider fallback & data provenance

- **Fallback chain** (historical + quote): Alpha Vantage → Yahoo Finance → (opt-in) deterministic mock. Fallback is triggered by `DATA_PROVIDER_RATE_LIMIT`, `DATA_PROVIDER_UNAVAILABLE`, or a timeout from the primary. `UNKNOWN_TICKER` and `INSUFFICIENT_HISTORY` do **not** fall back — they propagate as-is.
- **Rate-limit preservation**: if every configured provider fails with `DATA_PROVIDER_RATE_LIMIT` the service re-raises the rate-limit error (HTTP 429), **not** a generic unavailability. This lets clients back off intelligently instead of retrying blindly.
- **Provenance headers** (every `/api/quote`, `/api/historical`, `/api/risk-free-rate` response):
  - `X-Data-Source: ALPHA_VANTAGE | YAHOO | MOCK | CACHE | FALLBACK` — identifies the provider that actually produced the payload (or `CACHE` when served from SQLite, or `FALLBACK` for the static FRED rate).
  - `X-Data-Warnings: <comma-separated slugs>` — present only when a non-primary path was taken, e.g. `av_rate_limited,using_yahoo` or `fred_unavailable,using_fallback_rate`. The frontend uses this to render an inline banner in the *APIs & Data* tab.
- **Mock fallback is opt-in**: setting `USE_MOCK_FALLBACK=1` flips on the deterministic GBM generator in `app/data/mock.py`. It is seeded by ticker so the same ticker always returns the same series across runs. Never enabled by default in production; exists so CI and offline demos never block on provider availability.

### Target latencies (post-cache warm-up)

| Endpoint | Target p95 |
|---|---|
| `/quote` | < 150 ms |
| `/historical` | < 300 ms (cached) / < 2 s (cold) |
| `/risk-free-rate` | < 100 ms (cached) |
| `/optimize` (≤10 tickers, cold) | < 5 s |
| `/optimize` (≤10 tickers, warm) | < 500 ms |
| `/backtest` (5 years, monthly rebalance) | < 10 s |
| `/chat` (rule) | < 200 ms |
| `/chat` (LLM) | < 4 s |

### Error taxonomy

Every error response uses the shape `{ code: ErrorCode, message: string, details?: object }`. `ErrorCode` is an enum (enumerated in [CONTRACTS.md](CONTRACTS.md)) covering at minimum:

- `UNKNOWN_TICKER`, `INSUFFICIENT_HISTORY`, `DATA_PROVIDER_RATE_LIMIT`, `DATA_PROVIDER_UNAVAILABLE`
- `OPTIMIZER_INFEASIBLE`, `OPTIMIZER_NON_PSD_COVARIANCE`
- `INVALID_RISK_PROFILE`, `INVALID_RETURN_WINDOW`
- `LLM_UNAVAILABLE`, `INTERNAL`

Never leak raw 5xx bodies from upstream APIs to the client.

### Numerical correctness

See [../.cursor/rules/quant.mdc](../.cursor/rules/quant.mdc). Short version: all returns are annualized decimals (0.12 not 12%), no intermediate rounding, covariance matrices are projected to the nearest PSD matrix if numerical drift breaks positive-definiteness, optimizer constraints are declared per-call and never defaulted silently.

---

## 7. Environment variables

| Variable | Required? | Purpose |
|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | No† | Market data (primary). If unset or rate-limited, backend automatically falls back to Yahoo Finance. †Strongly recommended in production; Yahoo-only operation works but is slower and unversioned. |
| `FRED_API_KEY` | No | Risk-free rate via `DGS3MO`. If unset, backend uses a static fallback (`X-Data-Source: FALLBACK`, documented in UI with a warning). |
| `OPENAI_API_KEY` | No | Enables LLM fallback in `/chat`. If unset, chat stays rule-based only. |
| `USE_MOCK_FALLBACK` | No | `1` to enable the deterministic GBM mock as a last-resort fallback after Alpha Vantage → Yahoo both fail. Default `0`. |
| `RUN_LIVE_TESTS` | No | `1` to un-skip pytest tests marked `live` (hit real AV/FRED/Yahoo). Default `0`. |
| `PORT` | No | FastAPI port, default `8000`. |
| `CACHE_DB_PATH` | No | Default `backend/.cache/market.db`. |
| `CORS_ORIGINS` | No | Default `http://localhost:5173`. Comma-separated list. |

A `.env.example` will be produced in Phase 4. Downstream agents should NOT commit a real `.env`.

---

## 8. Glossary (authoritative symbol reference)

All symbols use these names and units throughout code, docs, and UI. Deviations fail review.

| Symbol | Code name | Meaning | Unit / sign |
|---|---|---|---|
| `E(r)` | `expected_return` / `expectedReturn` | Expected annualized return of an asset | Decimal (e.g. `0.12`) |
| `σ` | `std_dev` / `stdDev` | Annualized standard deviation of returns | Decimal ≥ 0 |
| `σ²` | `variance` | Annualized variance | Decimal ≥ 0 |
| `Cov(i,j)` | `covariance[i][j]` | Annualized covariance between asset `i` and `j` | Decimal, can be negative |
| `ρ(i,j)` | `correlation[i][j]` | Correlation in `[-1, 1]` | Decimal |
| `r_f` | `risk_free_rate` / `riskFreeRate` | Annualized yield on 3-month T-bill | Decimal |
| `E(r_M)` | `market_expected_return` / `marketExpectedReturn` | Annualized expected market return (SPY proxy) | Decimal |
| `σ_M` | `market_std_dev` / `marketStdDev` | Annualized market std dev | Decimal ≥ 0 |
| `β` | `beta` | Systematic-risk coefficient vs. market | Decimal, any sign |
| `σ²(e_i)` | `firm_specific_var` / `firmSpecificVar` | Residual (unsystematic) variance of asset `i` | Decimal ≥ 0 |
| `α` | `alpha` | Excess return vs. CAPM prediction | Decimal, any sign |
| `A` | `risk_aversion` / `A` | Client's risk-aversion coefficient | Integer `[1, 10]` |
| `y` | `y_star` / `yStar` | Fraction of wealth in the ORP (risky) | Decimal, can exceed 1 (leverage) or go negative (not supported in v1) |
| `w_i` | `weights[ticker]` | Weight of asset `i` in the ORP | Decimal, sum to 1 within the risky portion; individual weight can be negative (short) |
| `SR` | `sharpe` | Sharpe ratio of a portfolio `(E(r_p) - r_f) / σ_p` | Decimal |

---

## 9. Per-agent handoff checklist

Every downstream agent must (1) read all four Phase 0 files before writing code, (2) stay inside its allowed folder set, and (3) conform exactly to [CONTRACTS.md](CONTRACTS.md). Violations are blocking PR review comments, not style nits.

### Agent 1A — Backend Data Layer — branch `feat/backend-data`

- **Owns**: `backend/app/data/`, `backend/app/api/`, `backend/app/schemas.py`, `backend/app/errors.py`, `backend/app/settings.py`, `backend/app/main.py`, `backend/.cache/`, `backend/data/snapshots/`, tests for those folders.
- **Delivers**: `GET /api/quote`, `GET /api/historical`, `GET /api/risk-free-rate` end-to-end against live AV (primary), Yahoo (auto-fallback), and FRED. Every response carries `X-Data-Source` (and `X-Data-Warnings` on fallback).
- **Must honor**: Alpha Vantage rate limit (5/min, 500/day) via a token bucket + SQLite-backed daily counter; SQLite cache at `CACHE_DB_PATH` with single-flight coalescing; exact Pydantic shapes from [CONTRACTS.md](CONTRACTS.md); error codes from the error taxonomy; rate-limit error preservation across fallback (HTTP 429 when every provider is throttled).
- **Must NOT**: implement any math, any optimizer, any frontend, or touch `backend/quant/`.
- **Fixture verification**: Dataset B tickers in [FIXTURES.md](FIXTURES.md) must round-trip through `/api/historical` with matching SHA-256 on the canonical snapshot (`backend/data/snapshots/dataset_b.json`). The snapshot is provider-stable — the live-gated test asserts every ticker resolved through the same provider so the hash is not contaminated by mixing AV and Yahoo bars.

### Agent 1B — Frontend Scaffold — branch `feat/frontend-scaffold`

- **Owns**: `frontend/` in its entirety.
- **Delivers**: Vite + React + TS + Tailwind + Recharts + lucide-react app with all 5 tabs rendering, header with `A` slider + questionnaire toggle + target-return input, chat box UI shell, ticker add/remove bar. All data sourced from the `OptimizationResult` sample in [FIXTURES.md](FIXTURES.md) (inline JSON imported as a typed const). No backend calls.
- **Must honor**: TypeScript types in [CONTRACTS.md](CONTRACTS.md); visual baseline from the user's original component (colors, layout, icons).
- **Must NOT**: call any `/api` endpoints, implement chat logic, or touch `backend/`.

### Agent 1C — Quant Math Core — branch `feat/quant-core`

- **Owns**: `backend/quant/`, `backend/tests/quant/`.
- **Delivers**: Pure functions (no I/O) implementing every formula in [../.cursor/rules/quant.mdc](../.cursor/rules/quant.mdc). Minimum API: `expected_returns`, `covariance_matrix`, `sharpe_ratio`, `capm_required_return`, `single_index_metrics`, `optimize_markowitz` (must accept `allow_short` and `allow_leverage` flags), `optimize_single_index`, `utility_max_allocation`, `cal_points`, `efficient_frontier_points`. ≥ 90% test coverage; every math function has at least one test using Dataset A from [FIXTURES.md](FIXTURES.md).
- **Must honor**: no rounding of intermediates, PSD-projection on covariance, full-MPT defaults (never hardcode long-only).
- **Must NOT**: touch FastAPI, Alpha Vantage, SQLite, or any frontend code.

---

## 10. Definition of Done for Phase 0

Phase 0 ships when all four files below are committed to `main`:

- [docs/SPEC.md](SPEC.md) — this file
- [docs/CONTRACTS.md](CONTRACTS.md)
- [docs/FIXTURES.md](FIXTURES.md)
- [../.cursor/rules/quant.mdc](../.cursor/rules/quant.mdc)

No other files exist in the repo at the end of Phase 0. The next commit on `main` is the merge of Phase 1's first green PR.
