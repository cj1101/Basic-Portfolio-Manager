# Portfolio Manager — Backend Data Layer

Phase 1B deliverable (Agent 1A per [`docs/SPEC.md`](../docs/SPEC.md) §9). Ships the
data-layer modules and three read-only HTTP endpoints:

- `GET /api/quote?ticker=…`
- `GET /api/historical?ticker=…&frequency=daily&years=5`
- `GET /api/risk-free-rate`

`POST /api/optimize` and all higher-level endpoints are **deferred to Phase 2**.

## Stack

- Python 3.11+, FastAPI, Pydantic v2
- `uv` for dependency management (single `uv.lock`)
- `aiosqlite` SQLite cache at `CACHE_DB_PATH` (default `backend/.cache/market.db`)
- `httpx` async client for Alpha Vantage + FRED
- `yfinance` as the Alpha Vantage fallback (not primary — unofficial API)
- `pytest` + `pytest-asyncio` + `respx` for the test suite

## Provider chain

1. **Alpha Vantage** (primary). Rate-limited to 5 req/min, 500 req/day via a
   token-bucket limiter (`app/data/rate_limit.py`). SPEC §3 #4.
2. **Yahoo** (fallback). Activated when AV returns 429/5xx/network failure or
   when `ALPHA_VANTAGE_API_KEY` is missing.
3. **Mock** (opt-in). Only when `USE_MOCK_FALLBACK=true` AND both real providers
   fail. Produces deterministic seeded GBM bars so the frontend stays alive in
   demos. Defaults to **off** so production never serves fake data silently.

Every response carries an `X-Data-Source: alpha-vantage|yahoo|mock` header so
callers can audit provenance. The JSON body itself is byte-identical to the
shapes in [`docs/CONTRACTS.md`](../docs/CONTRACTS.md).

## Setup

```bash
cd backend
uv sync --extra dev
cp .env.example .env
# edit .env and set ALPHA_VANTAGE_API_KEY (and FRED_API_KEY if you have one)
```

## Running

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for the OpenAPI UI.

## Testing

### Offline (respx-mocked; no network, no keys required)

```bash
uv run pytest
```

### Live integration (hits Alpha Vantage, FRED, Yahoo)

```bash
$env:RUN_LIVE_TESTS = "1"
uv run pytest -m live
```

The Dataset B snapshot test (`tests/data/test_dataset_b.py`) is the only place
the backend ever calls the real APIs during tests. Once it runs, it:

1. Fetches `AAPL, MSFT, NVDA, JPM, XOM, SPY` for 5 years of daily bars.
2. Canonicalises to sorted-key JSON (LF, no trailing newline).
3. Writes `backend/data/snapshots/dataset_b.json`.
4. Computes the SHA-256 and patches [`docs/FIXTURES.md`](../docs/FIXTURES.md) §2
   `hashPlaceholder` in place.
5. All subsequent runs assert byte-exact equality against the locked hash.

### Coverage

```bash
uv run pytest --cov=app/data --cov-report=term-missing --cov-fail-under=90
```

## Environment variables

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | yes | — | Primary market data |
| `FRED_API_KEY` | no | — | Live risk-free rate (`DGS3MO`) |
| `OPENAI_API_KEY` | no | — | Unused in Phase 1B |
| `PORT` | no | `8000` | Uvicorn port |
| `CACHE_DB_PATH` | no | `backend/.cache/market.db` | SQLite cache location |
| `CORS_ORIGINS` | no | `http://localhost:5173` | Comma-separated |
| `USE_MOCK_FALLBACK` | no | `false` | Enable mock-provider last resort |
| `RUN_LIVE_TESTS` | no | `0` | Enables `@pytest.mark.live` tests |
