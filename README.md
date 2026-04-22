# Portfolio Manager — Phase 1A (Quant Engine)

This repository hosts the **Portfolio Manager** monorepo. Phase 1A delivers
the **Quant Engine** — pure math only, with two language implementations
that produce identical results on the golden dataset:

| Implementation        | Role                                    | Location              |
| --------------------- | --------------------------------------- | --------------------- |
| Python 3.11+ (source) | Reference / backend of record           | `backend/quant/`      |
| TypeScript (mirror)   | Client-side math + future shared bundle | `packages/quant-ts/`  |

Other concerns — data ingestion, FastAPI endpoints, React UI, charts,
chat — are **out of scope** for Phase 1A and are owned by sibling agents.
See `docs/SPEC.md` §9 for the full agent matrix.

## What Phase 1A includes

- `buildCovariance`, `nearestPsd`, `ensurePsdCovariance` (symmetry + PSD
  validation, minor-drift projection with warning).
- `expectedReturns`, `stdDevs`, `sampleCovariance`, annualization helpers.
- `sharpeRatio`.
- CAPM: `capmRequiredReturn`, `capmTotalExpectedReturn`,
  `capmSystematicVariance`, `capmTotalVariance`, `capmTotalStdDev`.
- Single-Index Model regression: `singleIndexMetrics` returning
  `(alpha, beta, σ²(e))`.
- `optimizeMarkowitz` (tangency / ORP): closed-form unconstrained, active-set
  long-only.
- `minimumVariancePortfolio` (MVP): closed-form unconstrained, active-set
  long-only.
- `utilityMaxAllocation`: `y* = (E(r_ORP) − rᶠ) / (A · σ²_ORP)` with
  target-return override, leverage clamp, warnings list.
- `efficientFrontierPoints` (Merton closed form), `calPoints` (Capital
  Allocation Line sampling).
- Typed errors (`QuantError` hierarchy) mapping onto the `ErrorCode` taxonomy
  from `docs/CONTRACTS.md` §2.

Every function is pure: no I/O, no network, no logging, no hidden globals.
Warnings are surfaced through an opt-in `warnings: string[]` parameter.

## Repository layout

```
automatedBrokerageClassVersion/
├── backend/
│   ├── pyproject.toml          # uv / hatchling; deps: numpy scipy cvxpy pydantic
│   ├── quant/                  # source of truth (Python)
│   │   ├── __init__.py         # public barrel re-exports
│   │   ├── types.py            # Pydantic models, camelCase aliases
│   │   ├── errors.py           # QuantError hierarchy + ErrorCode
│   │   ├── linalg.py           # covariance build / PSD / projection
│   │   ├── returns.py          # annualization + moments
│   │   ├── sharpe.py           # Sharpe ratio
│   │   ├── capm.py             # CAPM formulas
│   │   ├── sim.py              # Single-Index Model regression
│   │   ├── markowitz.py        # tangency (closed-form + cvxpy)
│   │   ├── minvar.py           # minimum-variance portfolio
│   │   ├── allocation.py       # utility-max allocation (y*)
│   │   └── frontier.py         # Merton frontier + CAL
│   └── tests/quant/            # pytest, one file per module + end-to-end
├── packages/
│   └── quant-ts/               # TypeScript mirror (@portfolio/quant)
│       ├── src/…               # 1:1 port, hand-rolled linalg (deterministic)
│       └── test/…              # vitest mirror of pytest
├── docs/                       # SPEC, CONTRACTS, FIXTURES
├── .cursor/rules/quant.mdc     # conventions for the quant layer
├── .github/workflows/ci.yml    # runs pytest + vitest in parallel
├── pnpm-workspace.yaml
└── package.json                # root scripts
```

Nothing under `frontend/`, `backend/api/`, `backend/data/`,
`backend/clients/` is created by this phase.

## Prerequisites

- **Python 3.11+** and `uv` (`pip install uv`).
- **Node 20+** and `pnpm 9+` (`npm i -g pnpm`).

Dependency pins:

- `numpy ≥ 2.0, <3`, `scipy ≥ 1.13, <2`, `cvxpy ≥ 1.5, <2`,
  `pydantic ≥ 2.7, <3`.
- `typescript 5.5`, `vitest 1.6`, `tsup 8.1`. TypeScript has **zero runtime
  dependencies** — the linear-algebra routines are hand-rolled for determinism.

## Run the whole product (one command)

```powershell
# From the repo root — starts FastAPI + Vite together with DEBUG logs,
# colored [backend]/[frontend] prefixes, and a timestamped log file in
# backend/.logs/dev-<stamp>.log.
pnpm dev:all
# or, without pnpm:
python scripts/dev.py
```

Useful flags:

```powershell
python scripts/dev.py --no-frontend          # just the API
python scripts/dev.py --no-backend           # just the UI
python scripts/dev.py --port 9000            # backend on :9000
python scripts/dev.py --log-level INFO       # less verbose
```

The backend chat endpoint uses **OpenRouter** for every LLM call. Configure
it via `backend/.env`:

```
OPENROUTER_API_KEY=sk-or-v1-…
OPENROUTER_MODEL=google/gemma-4-31b-it
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

The frontend Settings panel (gear icon in the header) lets you override the
model per-session — the list is fetched live from OpenRouter and cached on
the backend for 5 minutes.

## Running tests

### Python (backend)

```bash
cd backend
uv venv .venv
source .venv/bin/activate                # Windows: .venv\Scripts\Activate
uv pip install -e ".[dev]"

pytest                                    # runs suite + coverage gate ≥ 90%
ruff check quant tests
ruff format --check quant tests
mypy quant
```

The `pytest` invocation uses the config in `pyproject.toml`:

```
addopts = --cov=quant --cov-branch --cov-report=term-missing --cov-fail-under=90
```

### TypeScript (`@portfolio/quant`)

```bash
pnpm install                              # at repo root
pnpm --filter @portfolio/quant run typecheck
pnpm --filter @portfolio/quant run lint
pnpm --filter @portfolio/quant run test   # vitest + v8 coverage ≥ 90%
pnpm --filter @portfolio/quant run build  # tsup ESM+CJS+d.ts
```

Root-level convenience scripts run both packages:

```bash
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

## Parity guarantee

Both suites assert against Dataset A from
[`docs/FIXTURES.md`](docs/FIXTURES.md) §1 at `1e-6` tolerance on every
scalar and `1e-9` on weight sums. The fixture is declared once per
language:

- Python: `backend/tests/conftest.py`
- TypeScript: `packages/quant-ts/src/fixtures/datasetA.ts`

Because both implementations derive from the same closed-form math — and
because TypeScript uses hand-rolled LU solve + Jacobi eigendecomposition
rather than a third-party numerical backend — the two environments produce
results that match bit-for-bit on the Dataset A weights and within
`1e-12` on all moments.

## Explicit non-goals for Phase 1A

- **No HTTP surface.** FastAPI endpoints, request/response middleware,
  CORS, rate limiting, and caching are owned by a later phase
  (`backend/api/`).
- **No data layer.** Alpha Vantage, FRED, Redis/SQLite, snapshot files in
  `backend/data/` are Agent 1A's responsibility.
- **No UI.** React/Vite/Tailwind/Recharts, risk sliders, and PDF export
  are Agent 1C's responsibility.
- **No Dataset B tests.** Those require live Alpha Vantage and are pinned
  to a snapshot file that does not yet exist.
- **No backtester, no chat, no live rebalancing.**

## Conventions enforced by this phase

From [`.cursor/rules/quant.mdc`](.cursor/rules/quant.mdc):

- All math outputs are **annualized decimals**. Rounding happens at the
  response layer (not touched here).
- Covariance matrices are **symmetric** and **positive semi-definite**;
  minor drift is projected via `nearestPsd` and logged as a warning.
  Material non-PSD is rejected with `OPTIMIZER_NON_PSD_COVARIANCE`.
- Every optimizer accepts `allowShort` and (where relevant) `allowLeverage`
  as explicit arguments — never defaulted silently.
- Error codes match the universal taxonomy from `docs/CONTRACTS.md` §2.
- Wire format is **camelCase** on both sides; Python snake_case is an
  internal convenience via Pydantic aliasing.

## Glossary (quick reference)

| Symbol      | Meaning                                                           |
| ----------- | ----------------------------------------------------------------- |
| `rᶠ`        | risk-free rate (annualized decimal)                               |
| `μ`         | vector of expected annual returns                                 |
| `Σ`         | annual covariance matrix                                          |
| `β`, `α`    | CAPM beta and alpha                                               |
| `σ²(e)`     | firm-specific variance (single-index residual)                    |
| `A`         | risk-aversion coefficient (1–10 integer)                          |
| `ORP`       | Optimal Risky Portfolio (tangency)                                |
| `MVP`       | Minimum-Variance Portfolio                                        |
| `CAL`       | Capital Allocation Line                                           |
| `y*`        | optimal fraction in ORP per `U(y)` maximization                   |

See `docs/SPEC.md` §8 for the full glossary.
