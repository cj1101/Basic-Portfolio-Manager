# Portfolio Manager

Portfolio Manager is a full-stack portfolio analysis app for building, inspecting, and exporting equity portfolios from ticker symbols. It combines a FastAPI backend, a React + Vite frontend, and shared quant tooling inside a single monorepo.

The current codebase supports live market-data ingestion, Markowitz optimization, CAPM and course analytics, valuation workflows, technical analysis views, chat-assisted portfolio explanations, and Excel export.

## Highlights

- Ticker-driven portfolio workflow with configurable risk aversion and optional target return
- Live market data with Alpha Vantage as the primary source and Yahoo Finance fallback
- Risk-free rate support via FRED with documented fallback behavior
- Markowitz optimization with support for short positions and leverage
- Efficient frontier, CAL, CAPM/alpha, allocation, technical analysis, and data provenance views
- Course analytics endpoints for Treynor, Jensen alpha, SIM variance decomposition, holding-period returns, and Fama-French 3 output
- Valuation endpoints for FCFF, FCFE, and DDM analysis
- Hybrid chat assistant with rule-based responses and optional OpenRouter-backed LLM mode
- Excel export pipeline that rebuilds analytics into a workbook
- Shared TypeScript quant package in `packages/quant-ts`

## Monorepo layout

```text
.
|-- backend/          FastAPI API, data layer, optimization, analytics, export, chat
|-- frontend/         React + Vite dashboard
|-- packages/quant-ts Shared TypeScript quant utilities
|-- docs/             Product spec, contracts, fixtures
|-- scripts/          Local developer helpers
|-- package.json      Workspace scripts
`-- pnpm-workspace.yaml
```

## Tech stack

- Backend: Python 3.11+, FastAPI, Pydantic, NumPy, SciPy, CVXPY, pandas
- Frontend: React 18, TypeScript, Vite, Recharts, TanStack Query
- Package management: `pnpm` for JS/TS, `uv` for Python
- Data providers: Alpha Vantage, Yahoo Finance, FRED
- Optional LLM provider: OpenRouter

## Current feature set

### Frontend

- Executive summary dashboard
- Efficient frontier visualization
- CAPM and alpha breakdown
- Asset allocation and complete portfolio views
- Risk and valuation tab
- Technical analysis tab
- APIs and data provenance tab
- Chat panel with portfolio-aware context
- Settings flow for LLM/API key behavior

### Backend

- `GET /health`
- `GET /api/quote`
- `GET /api/historical`
- `GET /api/risk-free-rate`
- `POST /api/optimize`
- `POST /api/analytics/performance`
- `POST /api/valuation`
- `POST /api/chat`
- `GET /api/chat/sessions/{sessionId}`
- `POST /api/chat/sessions/{sessionId}/messages`
- `DELETE /api/chat/sessions/{sessionId}`
- `GET /api/llm/models`
- `GET /api/llm/default`
- `PATCH /api/settings/api-keys`
- `POST /api/export`

## Prerequisites

Install these before running the project:

- Python `3.11+`
- Node.js `20+`
- `pnpm` `9+`
- `uv`

Version checks:

```bash
python --version
node --version
pnpm --version
uv --version
```

## Getting started

### 1. Clone the repository

```bash
git clone https://github.com/cj1101/Basic-Portfolio-Manager.git
cd Basic-Portfolio-Manager
```

If you cloned from a different remote name or local folder, use that folder instead.

### 2. Install JavaScript dependencies

```bash
pnpm install
```

### 3. Install Python dependencies

```bash
cd backend
uv sync --extra dev
cd ..
```

### 4. Create your environment file

Windows PowerShell:

```powershell
Copy-Item backend\.env.example backend\.env
```

macOS/Linux:

```bash
cp backend/.env.example backend/.env
```

### 5. Configure environment variables

Open `backend/.env` and set the values you need.

Required for normal live usage:

- `ALPHA_VANTAGE_API_KEY`

Optional but important:

- `FRED_API_KEY` for live 3-month T-bill data
- `OPENROUTER_API_KEY` to enable LLM chat mode
- `OPENROUTER_MODEL` to set the default chat model
- `USE_MOCK_FALLBACK=true` if you want demo-safe synthetic data when real providers fail

Important startup note:

- The backend expects `ALPHA_VANTAGE_API_KEY` unless `USE_MOCK_FALLBACK=true`
- If no `OPENROUTER_API_KEY` is set, chat remains available in rule-based mode only

## Running the project

### Recommended: start frontend and backend together

From the repo root:

```bash
pnpm dev:all
```

This starts:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

### Run only one side

Backend only:

```bash
pnpm dev:backend
```

Frontend only:

```bash
pnpm dev:frontend
```

### Run the launcher directly

```bash
python scripts/dev.py
python scripts/dev.py --no-frontend
python scripts/dev.py --no-backend
python scripts/dev.py --port 9000
```

The launcher:

- starts both services
- prefixes logs by process
- writes combined logs to `backend/.logs/`
- switches backend ports when `8000` is already occupied

## Platform-specific setup notes

### Windows

- Use PowerShell or Windows Terminal
- `Copy-Item` is the simplest way to create `backend\.env`
- The dev launcher supports Windows process cleanup and port handling

### macOS

- Use Terminal or iTerm
- Standard `cp` commands work for `.env`
- `lsof` may be used by the launcher for port detection

### Linux

- Use your preferred shell
- Standard `cp` commands work for `.env`
- Ensure build tools required by Python dependencies are available if your distro is minimal

## Workspace scripts

From the repo root:

```bash
pnpm dev
pnpm dev:all
pnpm dev:backend
pnpm dev:frontend
pnpm build
pnpm test
pnpm typecheck
pnpm lint
pnpm bench
pnpm test:e2e
pnpm test:e2e:install
```

## Package-level scripts

### Backend

From `backend/`:

```bash
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run pytest -m live
```

### Frontend

From `frontend/`:

```bash
pnpm dev
pnpm build
pnpm test
pnpm test:e2e
```

### Shared quant package

From `packages/quant-ts/`:

```bash
pnpm build
pnpm test
pnpm typecheck
pnpm lint
```

## API overview

The backend is mounted under `/api`. The frontend defaults to calling `/api` through the Vite dev proxy.

For production or custom deployment, you can set `VITE_API_BASE_URL`. If you pass an absolute origin, the frontend appends `/api` when needed.

Useful endpoints:

- `/api/quote` for latest price snapshots
- `/api/historical` for historical bars by ticker, frequency, and lookback
- `/api/risk-free-rate` for the current 3-month T-bill proxy
- `/api/optimize` for the core optimization pipeline
- `/api/analytics/performance` for course analytics
- `/api/valuation` for valuation workflows
- `/api/chat` and `/api/chat/sessions/...` for chat flows
- `/api/export` for Excel workbook export

Interactive API docs are available at:

- `http://127.0.0.1:8000/docs`

## Data providers and fallbacks

- Alpha Vantage is the primary market-data source
- Yahoo Finance is the automatic fallback for quotes and historical data
- FRED powers the live risk-free rate when configured
- A deterministic mock fallback can be enabled for demos and degraded network scenarios

Response headers expose provenance:

- `X-Data-Source`
- `X-Data-Warnings`

## Testing and quality checks

Run all workspace checks from the repo root:

```bash
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Backend live tests:

Windows PowerShell:

```powershell
$env:RUN_LIVE_TESTS = "1"
uv run pytest -m live
```

macOS/Linux:

```bash
RUN_LIVE_TESTS=1 uv run pytest -m live
```

E2E browser tests:

```bash
pnpm test:e2e:install
pnpm test:e2e
```

## Configuration reference

Primary variables in `backend/.env`:

- `ALPHA_VANTAGE_API_KEY`
- `FRED_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_APP_TITLE`
- `PORT`
- `CACHE_DB_PATH`
- `CORS_ORIGINS`
- `USE_MOCK_FALLBACK`
- `RUN_LIVE_TESTS`

## Documentation

Project reference docs live in `docs/`:

- `docs/SPEC.md`
- `docs/CONTRACTS.md`
- `docs/FIXTURES.md`

Additional package docs:

- `backend/README.md`
- `frontend/README.md`

## Troubleshooting

- `pnpm` not found: install it globally with `npm install -g pnpm`
- `uv` not found: install it with `pip install uv`
- Backend fails at startup: confirm `ALPHA_VANTAGE_API_KEY` is set, or enable `USE_MOCK_FALLBACK=true`
- Chat LLM toggle is unavailable: confirm `OPENROUTER_API_KEY` is set
- Frontend cannot reach the API: verify the backend is running and check `VITE_API_BASE_URL`
- Requests are rate-limited: wait and retry, or inspect `Retry-After`, `X-Data-Source`, and `X-Data-Warnings`

## Status

This repository is an actively evolving monorepo. The README reflects the current implemented app structure and feature surface in this checkout, including optimization, analytics, valuation, chat, technical analysis, and export support.
