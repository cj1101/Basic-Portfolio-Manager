# Portfolio Manager

Monorepo for a portfolio-analysis app with:

- `backend`: FastAPI service (market data, optimization endpoints, chat support).
- `frontend`: React + Vite dashboard.
- `packages/quant-ts`: shared TypeScript quant/math package.

This README is the fastest path to get the project running from a fresh GitHub clone.

## 1) Prerequisites

Install these tools first:

- Python `3.11+`
- Node.js `20+`
- `pnpm` `9+` (`npm i -g pnpm`)
- `uv` for Python env/deps (`pip install uv`)

Check versions:

```powershell
python --version
node --version
pnpm --version
uv --version
```

## 2) Clone the repository

```powershell
git clone <your-repo-url>
cd automatedBrokerageClassVersion
```

## 3) Install dependencies

Install JS/TS workspace dependencies from the repo root:

```powershell
pnpm install
```

Install Python backend dependencies:

```powershell
cd backend
uv sync --extra dev
cd ..
```

## 4) Configure environment variables

Create backend env file from template:

```powershell
copy backend\.env.example backend\.env
```

Open `backend/.env` and set at least:

- `ALPHA_VANTAGE_API_KEY` (required for market data endpoints)

Optional but recommended:

- `FRED_API_KEY`
- `OPENROUTER_API_KEY` (enables LLM responses in chat)

## 5) Run the app (backend + frontend)

From repo root:

```powershell
pnpm dev:all
```

This starts:

- Backend API at `http://localhost:8000`
- Frontend app at `http://localhost:5173`

Useful variants:

```powershell
pnpm dev:backend   # backend only
pnpm dev:frontend  # frontend only
python scripts/dev.py --port 9000
```

## 6) Run tests and quality checks

From repo root:

```powershell
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Backend-only tests:

```powershell
cd backend
uv run pytest
cd ..
```

Frontend-only tests:

```powershell
cd frontend
pnpm test
cd ..
```

## 7) Common issues

- `pnpm` not found: run `npm i -g pnpm`.
- `uv` not found: run `pip install uv`.
- Backend starts but requests fail: verify `ALPHA_VANTAGE_API_KEY` in `backend/.env`.
- CORS/API URL issues in production: set `VITE_API_BASE_URL` for the frontend.

## Useful paths

- Root scripts: `package.json`
- Dev launcher: `scripts/dev.py`
- Backend docs: `backend/README.md`
- Frontend docs: `frontend/README.md`
- Product spec and contracts: `docs/SPEC.md`, `docs/CONTRACTS.md`
