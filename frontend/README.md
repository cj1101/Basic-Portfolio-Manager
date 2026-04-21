# Portfolio Manager — Frontend (Phase 1 Agent C)

Vite + React 18 + TypeScript + Tailwind + Recharts. This package renders the
client-facing portfolio report. It is **entirely fixture-driven** in Phase 1:
no network calls, no live API keys, no backend dependency.

## Quick start

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/`. All five tabs, the risk-aversion slider, the
ticker input, and the (disabled) chat pane should render without any
configuration.

## Scripts

| Script              | Purpose                                        |
| ------------------- | ---------------------------------------------- |
| `npm run dev`       | Vite dev server at port 5173                   |
| `npm run build`     | Typecheck + production build into `dist/`     |
| `npm run preview`   | Serve the production build locally             |
| `npm run typecheck` | `tsc --noEmit` across `src/` and `tests/`     |
| `npm run lint`      | ESLint (typescript-eslint strict + Prettier)   |
| `npm run test`      | Vitest smoke tests                             |
| `npm run format`    | Prettier-write                                 |

## Layout

```
src/
  main.tsx                     # wires <PortfolioProvider> and mounts the app
  App.tsx                      # header + intro + controls + tabs + chat
  types/contracts.ts           # single source of truth (mirrors docs/CONTRACTS.md)
  fixtures/                    # phase-1 only data
  lib/                         # pure display-layer helpers (format, CAL, SML, CP)
  state/portfolioContext.tsx   # tickers + riskProfile + live complete portfolio
  components/                  # Header, TickerBar, RiskControls, Questionnaire, Tabs, ChatShell
    tabs/                      # one file per tab
    charts/                    # EfficientFrontier, SML, CAL, Weights
    kpi/                       # KpiCard, MetricsTable
    ui/                        # Badge, Tooltip, Slider, NumberInput, EmptyState
tests/                         # Vitest + Testing-Library smoke tests
```

## Phase 1 constraints

- No `/api` client, no `fetch`. The only data source is
  `src/fixtures/optimizationResultSample.ts`, transcribed from
  `docs/FIXTURES.md` §3.
- The A slider and target-return input **locally recompute** the
  `CompletePortfolio` from the fixture's immutable ORP using the formula in
  `.cursor/rules/quant.mdc` §4. This is display math, not optimizer math.
- User-added tickers appear as "Pending — Phase 2" chips. They don't affect
  any chart or table.
- All financial values flow through `lib/format.ts`; percent strings exist
  only at the UI boundary.
