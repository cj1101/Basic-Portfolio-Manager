# Contracts — Shared Types & API Schema (CONTRACTS.md)

> **This is a Phase 0 artifact.** Every type below is binding: Pydantic models (backend) and TypeScript types (frontend) MUST match field-for-field, name-for-name (respecting Python's `snake_case` vs TypeScript's `camelCase` — the Pydantic layer uses `alias_generator=to_camel` so the wire format is always `camelCase`).
>
> If a downstream agent needs a shape that is not defined here, the correct action is to **stop, open a PR editing this file first**, get it approved, and only then implement. No field additions in application code.

Contents:

1. [Conventions](#1-conventions)
2. [Enumerations](#2-enumerations)
3. [Domain types](#3-domain-types)
4. [Request / response envelopes](#4-request--response-envelopes)
5. [Endpoints](#5-endpoints)
6. [Wire-format rules](#6-wire-format-rules)

---

## 1. Conventions

- **Wire format**: JSON, `camelCase` keys, UTF-8, all numbers as IEEE-754 doubles.
- **Timestamps**: ISO-8601 UTC strings, e.g. `"2024-11-21T00:00:00Z"`. Dates without time use `"YYYY-MM-DD"`.
- **Decimals**: all monetary amounts and return/variance/weight scalars are JSON numbers. Returns are annualized decimals (`0.12`, never `12` or `"12%"`).
- **Maps keyed by ticker**: `Record<Ticker, T>` where `Ticker` is the uppercase symbol.
- **Optional fields**: explicit `?` / `Optional[...]`; `null` is permitted on the wire; omitted and `null` are equivalent.
- **Rounding**: responses round all scalar fields to 6 decimal places at serialization time ONLY. Intermediate computations never round.
- **Error shape** (universal, non-2xx responses):
  ```json
  { "code": "UNKNOWN_TICKER", "message": "Unknown ticker: FOO", "details": { "ticker": "FOO" } }
  ```

---

## 2. Enumerations

### `ReturnFrequency`

```python
# Python
class ReturnFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
```

```ts
// TypeScript
export type ReturnFrequency = "daily" | "weekly" | "monthly";
```

### `ErrorCode`

```python
class ErrorCode(str, Enum):
    UNKNOWN_TICKER = "UNKNOWN_TICKER"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    DATA_PROVIDER_RATE_LIMIT = "DATA_PROVIDER_RATE_LIMIT"
    DATA_PROVIDER_UNAVAILABLE = "DATA_PROVIDER_UNAVAILABLE"
    OPTIMIZER_INFEASIBLE = "OPTIMIZER_INFEASIBLE"
    OPTIMIZER_NON_PSD_COVARIANCE = "OPTIMIZER_NON_PSD_COVARIANCE"
    INVALID_RISK_PROFILE = "INVALID_RISK_PROFILE"
    INVALID_RETURN_WINDOW = "INVALID_RETURN_WINDOW"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    INVALID_VALUATION = "INVALID_VALUATION"
    INTERNAL = "INTERNAL"
```

```ts
export type ErrorCode =
  | "UNKNOWN_TICKER"
  | "INSUFFICIENT_HISTORY"
  | "DATA_PROVIDER_RATE_LIMIT"
  | "DATA_PROVIDER_UNAVAILABLE"
  | "OPTIMIZER_INFEASIBLE"
  | "OPTIMIZER_NON_PSD_COVARIANCE"
  | "INVALID_RISK_PROFILE"
  | "INVALID_RETURN_WINDOW"
  | "LLM_UNAVAILABLE"
  | "INVALID_VALUATION"
  | "INTERNAL";
```

### `ChatSource`

```python
class ChatSource(str, Enum):
    RULE = "rule"
    LLM = "llm"
```

```ts
export type ChatSource = "rule" | "llm";
```

### `ChatMode`

Client-selected routing mode for the hybrid chat engine. `auto` is the default (rule-first, LLM fallback when configured). `rule` locks the engine to the rule-based intent classifier. `llm` forces the OpenAI path and returns `LLM_UNAVAILABLE` when `OPENAI_API_KEY` is unset.

```python
class ChatMode(str, Enum):
    AUTO = "auto"
    RULE = "rule"
    LLM = "llm"
```

```ts
export type ChatMode = "auto" | "rule" | "llm";
```

---

## 3. Domain types

### `Ticker`

A string. 1–10 uppercase letters/digits/dots. Examples: `"AAPL"`, `"BRK.B"`.

```python
Ticker = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9.]{1,10}$")]
```

```ts
export type Ticker = string;
```

### `PriceBar`

One daily OHLCV bar (adjusted close).

```python
class PriceBar(BaseModel):
    date: date                          # "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float                        # adjusted close
    volume: int
```

```ts
export interface PriceBar {
  date: string;     // "YYYY-MM-DD"
  open: number;
  high: number;
  low: number;
  close: number;    // adjusted close
  volume: number;
}
```

### `Quote`

Latest snapshot for one ticker.

```python
class Quote(BaseModel):
    ticker: Ticker
    price: float
    as_of: datetime
```

```ts
export interface Quote {
  ticker: Ticker;
  price: number;
  asOf: string;     // ISO-8601 UTC
}
```

### `StockMetrics`

Per-stock estimated statistics over the requested return window.

```python
class StockMetrics(BaseModel):
    ticker: Ticker
    expected_return: float              # E(r_i), annualized decimal
    std_dev: float                      # σ_i, annualized decimal
    beta: float                         # β_i vs. SPY
    alpha: float                        # α_i = mean(excess_i) - β_i * mean(excess_M)
    firm_specific_var: float            # σ²(e_i), annualized decimal
    n_observations: int                 # sample count used
```

```ts
export interface StockMetrics {
  ticker: Ticker;
  expectedReturn: number;
  stdDev: number;
  beta: number;
  alpha: number;
  firmSpecificVar: number;
  nObservations: number;
}
```

### `MarketMetrics`

Benchmark statistics over the same window used for stock metrics (proxied by SPY).

```python
class MarketMetrics(BaseModel):
    expected_return: float              # E(r_M)
    std_dev: float                      # σ_M
    variance: float                     # σ²_M
```

```ts
export interface MarketMetrics {
  expectedReturn: number;
  stdDev: number;
  variance: number;
}
```

### `CovarianceMatrix`

Dense matrix, symmetric, PSD. Rows and columns are labeled by `tickers`.

```python
class CovarianceMatrix(BaseModel):
    tickers: list[Ticker]
    matrix: list[list[float]]           # shape [n][n]
```

```ts
export interface CovarianceMatrix {
  tickers: Ticker[];
  matrix: number[][];        // shape [n][n]
}
```

### `CorrelationMatrix`

Dense **correlation** matrix: symmetric, unit diagonal, entries in `[-1, 1]`. Same row/column labels and ordering as `CovarianceMatrix` for a given run (`ρᵢⱼ = Covᵢⱼ / (σᵢ σⱼ)` with `σᵢ² = Varᵢ` on the diagonal of the paired covariance matrix).

```python
class CorrelationMatrix(BaseModel):
    tickers: list[Ticker]
    matrix: list[list[float]]           # shape [n][n]
```

```ts
export interface CorrelationMatrix {
  tickers: Ticker[];
  matrix: number[][];        // shape [n][n]
}
```

### `RiskProfile`

The client's personalization inputs.

```python
class RiskProfile(BaseModel):
    risk_aversion: int = Field(ge=1, le=10)         # A
    target_return: float | None = None              # annualized decimal, optional
```

```ts
export interface RiskProfile {
  riskAversion: number;       // integer in [1, 10]
  targetReturn?: number;      // annualized decimal
}
```

### `OptimizationResult`

The full output of `/optimize`. This is the shape the frontend binds every chart to.

```python
class FrontierPoint(BaseModel):
    std_dev: float
    expected_return: float

class CALPoint(BaseModel):
    std_dev: float
    expected_return: float
    y: float                            # share of ORP on this point

class ORP(BaseModel):
    weights: dict[Ticker, float]        # sum to 1; individual values may be negative (short)
    expected_return: float              # E(r_ORP)
    std_dev: float                      # σ_ORP
    variance: float                     # σ²_ORP
    sharpe: float

class CompletePortfolio(BaseModel):
    y_star: float                       # fraction in ORP; > 1 means leverage
    weight_risk_free: float             # = 1 - y_star
    weights: dict[Ticker, float]        # = y_star * orp.weights for risky, risk-free split reported separately
    expected_return: float
    std_dev: float
    leverage_used: bool

class OptimizationResult(BaseModel):
    request_id: str
    as_of: datetime
    risk_free_rate: float
    market: MarketMetrics
    stocks: list[StockMetrics]
    covariance: CovarianceMatrix
    correlation: CorrelationMatrix
    orp: ORP
    complete: CompletePortfolio
    frontier_points: list[FrontierPoint]
    cal_points: list[CALPoint]
    warnings: list[str] = []
```

```ts
export interface FrontierPoint { stdDev: number; expectedReturn: number; }

export interface CALPoint {
  stdDev: number;
  expectedReturn: number;
  y: number;
}

export interface ORP {
  weights: Record<Ticker, number>;
  expectedReturn: number;
  stdDev: number;
  variance: number;
  sharpe: number;
}

export interface CompletePortfolio {
  yStar: number;
  weightRiskFree: number;
  weights: Record<Ticker, number>;
  expectedReturn: number;
  stdDev: number;
  leverageUsed: boolean;
}

export interface OptimizationResult {
  requestId: string;
  asOf: string;
  riskFreeRate: number;
  market: MarketMetrics;
  stocks: StockMetrics[];
  covariance: CovarianceMatrix;
  correlation: CorrelationMatrix;
  orp: ORP;
  complete: CompletePortfolio;
  frontierPoints: FrontierPoint[];
  calPoints: CALPoint[];
  warnings: string[];
}
```

### `Portfolio` / `SavedPortfolio`

Saved-portfolio storage types.

```python
class Portfolio(BaseModel):
    name: str
    tickers: list[Ticker]
    risk_profile: RiskProfile
    return_frequency: ReturnFrequency = ReturnFrequency.DAILY
    lookback_years: int = 5
    allow_short: bool = True
    allow_leverage: bool = True

class SavedPortfolio(Portfolio):
    id: str
    created_at: datetime
    updated_at: datetime
    last_result: OptimizationResult | None = None
```

```ts
export interface Portfolio {
  name: string;
  tickers: Ticker[];
  riskProfile: RiskProfile;
  returnFrequency?: ReturnFrequency;      // default "daily"
  lookbackYears?: number;                 // default 5
  allowShort?: boolean;                   // default true
  allowLeverage?: boolean;                // default true
}

export interface SavedPortfolio extends Portfolio {
  id: string;
  createdAt: string;
  updatedAt: string;
  lastResult?: OptimizationResult;
}
```

### `BacktestResult`

```python
class EquityPoint(BaseModel):
    date: date
    equity: float                       # normalized to 1.0 at start

class BacktestResult(BaseModel):
    equity_curve: list[EquityPoint]
    realized_return: float              # annualized
    realized_std_dev: float
    realized_sharpe: float
    max_drawdown: float                 # negative decimal, e.g. -0.25
    rebalance_count: int
    compared_to_spy: EquityPoint        # last point, for reference
```

```ts
export interface EquityPoint { date: string; equity: number; }

export interface BacktestResult {
  equityCurve: EquityPoint[];
  realizedReturn: number;
  realizedStdDev: number;
  realizedSharpe: number;
  maxDrawdown: number;
  rebalanceCount: number;
  comparedToSpy: EquityPoint;
}
```

### `HoldingPeriodMonthlyReturns`

Arithmetic and **geometric mean monthly return** (both **per-month decimals**, *not* annualized) over the last 36, 60, and 120 **calendar month-ends** of adjusted closes. `R_t = P_t / P_{t-1} − 1` on month-end **simple** returns.

```python
class HoldingPeriodMonthlyReturns(BaseModel):
    years: int                          # 3, 5, or 10
    n_observations: int
    window_start: date
    window_end: date
    arithmetic_mean_monthly_return: float
    geometric_mean_monthly_return: float
```

```ts
export interface HoldingPeriodMonthlyReturns {
  years: 3 | 5 | 10;
  nObservations: number;
  windowStart: string;
  windowEnd: string;
  arithmeticMeanMonthlyReturn: number;
  geometricMeanMonthlyReturn: number;
}
```

### `ORPPerformanceMetrics` / `CompletePerformanceMetrics`

```python
class ORPPerformanceMetrics(BaseModel):
    treynor: float
    jensen_alpha: float
    n_observations: int
    total_variance: float
    systematic_variance: float
    unsystematic_variance: float
    sim_variance_mismatch: float

class CompletePerformanceMetrics(BaseModel):
    treynor: float
    jensen_alpha: float
    n_observations: int
    total_variance: float
    systematic_variance: float
    unsystematic_variance: float
    sim_variance_mismatch: float
```

```ts
export interface ORPPerformanceMetrics {
  treynor: number;
  jensenAlpha: number;
  nObservations: number;
  totalVariance: number;
  systematicVariance: number;
  unsystematicVariance: number;
  simVarianceMismatch: number;
}

export interface CompletePerformanceMetrics {
  treynor: number;
  jensenAlpha: number;
  nObservations: number;
  totalVariance: number;
  systematicVariance: number;
  unsystematicVariance: number;
  simVarianceMismatch: number;
}
```

### `FamaFrenchThreePerTicker`

```python
class FamaFrenchThreePerTicker(BaseModel):
    ticker: Ticker
    beta_mkt: float
    beta_smb: float
    beta_hml: float
    alpha: float
    n_observations: int
    expected_return_ff3: float
    expected_return_capm: float
```

```ts
export interface FamaFrenchThreePerTicker {
  ticker: Ticker;
  betaMkt: number;
  betaSmb: number;
  betaHml: number;
  alpha: number;
  nObservations: number;
  expectedReturnFf3: number;
  expectedReturnCapm: number;
}
```

### `AnalyticsPerformanceRequest` / `AnalyticsPerformanceResult`

```python
class AnalyticsPerformanceRequest(BaseModel):
    tickers: list[Ticker] = Field(min_length=2, max_length=30)
    orp_weights: dict[Ticker, float]
    return_frequency: ReturnFrequency = ReturnFrequency.DAILY
    lookback_years: int = Field(default=5, ge=1, le=20)
    y_star: float | None = None
    weight_risk_free: float | None = None

class AnalyticsPerformanceResult(BaseModel):
    as_of: datetime
    window_start: date
    window_end: date
    risk_free_rate: float
    data_source: str
    orp: ORPPerformanceMetrics
    complete: CompletePerformanceMetrics | None = None
    holding: list[HoldingPeriodMonthlyReturns]
    fama_french: list[FamaFrenchThreePerTicker]
    market: MarketMetrics
    warnings: list[str] = []
```

```ts
export interface AnalyticsPerformanceRequest {
  tickers: Ticker[];
  orpWeights: Record<Ticker, number>;
  returnFrequency?: ReturnFrequency;
  lookbackYears?: number;
  yStar?: number;
  weightRiskFree?: number;
}

export interface AnalyticsPerformanceResult {
  asOf: string;
  windowStart: string;
  windowEnd: string;
  riskFreeRate: number;
  dataSource: string;
  orp: ORPPerformanceMetrics;
  complete?: CompletePerformanceMetrics;
  holding: HoldingPeriodMonthlyReturns[];
  famaFrench: FamaFrenchThreePerTicker[];
  market: MarketMetrics;
  warnings: string[];
}
```

### `ValuationRequest` / `ValuationResult`

```python
class DdmTwoStageParams(BaseModel):
    g1: float
    g2: float
    n_periods: int = Field(ge=1, le=200)

class ValuationRequest(BaseModel):
    tickers: list[Ticker] = Field(min_length=1, max_length=20)
    wacc: float | None = None
    fcff_growth: float | None = None
    fcff_terminal_growth: float | None = None
    cost_of_equity_override: float | None = None
    ddm_gordon_g: float | None = None
    ddm_two_stage: DdmTwoStageParams | None = None

class TickerValuationBlock(BaseModel):
    ticker: Ticker
    fcff: float | None
    fcfe: float | None
    fcff_value_per_share: float | None
    fcfe_value_per_share: float | None
    ddm_gordon: float | None
    ddm_two_stage: float | None
    cost_of_equity: float
    warnings: list[str] = []

class ValuationResult(BaseModel):
    as_of: datetime
    per_ticker: list[TickerValuationBlock]
    data_source: str
    warnings: list[str] = []
```

```ts
export interface DdmTwoStageParams { g1: number; g2: number; nPeriods: number; }

export interface ValuationRequest {
  tickers: Ticker[];
  wacc?: number;
  fcffGrowth?: number;
  fcffTerminalGrowth?: number;
  costOfEquityOverride?: number;
  ddmGordonG?: number;
  ddmTwoStage?: DdmTwoStageParams;
}

export interface TickerValuationBlock {
  ticker: Ticker;
  fcff: number | null;
  fcfe: number | null;
  fcffValuePerShare: number | null;
  fcfeValuePerShare: number | null;
  ddmGordon: number | null;
  ddmTwoStage: number | null;
  costOfEquity: number;
  warnings: string[];
}

export interface ValuationResult {
  asOf: string;
  perTicker: TickerValuationBlock[];
  dataSource: string;
  warnings: string[];
}
```

### `DriftReport`

```python
class Drift(BaseModel):
    ticker: Ticker
    target_weight: float
    current_weight: float
    drift: float                        # current - target

class DriftReport(BaseModel):
    portfolio_id: str
    as_of: datetime
    total_drift: float                  # L1 sum of |drift|
    drifts: list[Drift]
    needs_rebalance: bool
```

```ts
export interface Drift {
  ticker: Ticker;
  targetWeight: number;
  currentWeight: number;
  drift: number;
}

export interface DriftReport {
  portfolioId: string;
  asOf: string;
  totalDrift: number;
  drifts: Drift[];
  needsRebalance: boolean;
}
```

### `ChatRequest` / `ChatResponse`

```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    portfolio_context: OptimizationResult | None = None
    mode: ChatMode = ChatMode.AUTO
    session_id: str | None = None        # opaque client-owned UUID; when set, server persists the turn

class ChatCitation(BaseModel):
    label: str                          # e.g. "ORP weight for NVDA"
    value: str                          # e.g. "0.1842"

class ChatResponse(BaseModel):
    answer: str
    source: ChatSource
    citations: list[ChatCitation] = []
```

```ts
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  portfolioContext?: OptimizationResult;
  mode?: ChatMode;                  // default "auto"
  sessionId?: string;
}

export interface ChatCitation { label: string; value: string; }

export interface ChatResponse {
  answer: string;
  source: ChatSource;
  citations: ChatCitation[];
}
```

### `ChatHistoryEntry` / `ChatSessionResponse`

Server-persisted chat log. Keyed by an opaque `sessionId` (client-generated UUID stored in `localStorage`). The `portfolioId` field is optional and reserved for Phase 3C Multi-portfolio (forward-compatible FK).

```python
class ChatHistoryEntry(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    source: ChatSource | None = None      # null on user turns
    citations: list[ChatCitation] = []
    created_at: datetime

class ChatSessionResponse(BaseModel):
    session_id: str
    portfolio_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatHistoryEntry]
```

```ts
export interface ChatHistoryEntry {
  role: "user" | "assistant";
  content: string;
  source?: ChatSource;                  // undefined on user turns
  citations: ChatCitation[];
  createdAt: string;                    // ISO-8601 UTC
}

export interface ChatSessionResponse {
  sessionId: string;
  portfolioId?: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatHistoryEntry[];
}
```

---

## 4. Request / response envelopes

### `OptimizationRequest`

```python
class OptimizationRequest(BaseModel):
    tickers: list[Ticker] = Field(min_length=2, max_length=30)
    risk_profile: RiskProfile
    return_frequency: ReturnFrequency = ReturnFrequency.DAILY
    lookback_years: int = Field(default=5, ge=1, le=20)
    allow_short: bool = True
    allow_leverage: bool = True
    alpha_overrides: dict[Ticker, float] | None = None       # reserved; not used in v1
    frontier_resolution: int = Field(default=40, ge=5, le=200)
```

```ts
export interface OptimizationRequest {
  tickers: Ticker[];
  riskProfile: RiskProfile;
  returnFrequency?: ReturnFrequency;
  lookbackYears?: number;
  allowShort?: boolean;
  allowLeverage?: boolean;
  alphaOverrides?: Record<Ticker, number>;
  frontierResolution?: number;
}
```

### `BacktestRequest`

```python
class BacktestRequest(BaseModel):
    portfolio: Portfolio
    start_date: date
    end_date: date
    rebalance: Literal["monthly", "quarterly", "yearly", "none"] = "monthly"
    initial_equity: float = 1.0
```

```ts
export interface BacktestRequest {
  portfolio: Portfolio;
  startDate: string;
  endDate: string;
  rebalance?: "monthly" | "quarterly" | "yearly" | "none";
  initialEquity?: number;
}
```

### `CompareRequest`

```python
class CompareRequest(BaseModel):
    portfolio_ids: list[str] = Field(min_length=2, max_length=5)
```

```ts
export interface CompareRequest {
  portfolioIds: string[];        // 2..5
}
```

### `AnalyticsPerformanceRequest` / `ValuationRequest`

See [§3 domain types](#driftreport) (`AnalyticsPerformanceRequest`, `ValuationRequest`, `DdmTwoStageParams`) — the wire shapes are identical; they are listed here for endpoint discoverability.

---

## 5. Endpoints

All endpoints are mounted under `/api`. Success is `200 OK` with the `Response` schema; errors use the universal error shape with appropriate HTTP status (`400/404/429/500/502/503`).

### 5.1 `GET /api/quote?ticker=AAPL` → `Quote`

Returns the latest available price for `ticker`.

Example response:

```json
{
  "ticker": "AAPL",
  "price": 182.52,
  "asOf": "2024-11-21T21:00:00Z"
}
```

### 5.2 `GET /api/historical?ticker=AAPL&frequency=daily&years=5` → `{ ticker: Ticker, frequency: ReturnFrequency, bars: PriceBar[] }`

Cache-friendly. `frequency` defaults to `daily`, `years` defaults to `5`.

Example (truncated):

```json
{
  "ticker": "AAPL",
  "frequency": "daily",
  "bars": [
    { "date": "2019-11-22", "open": 65.64, "high": 65.82, "low": 65.49, "close": 65.81, "volume": 16331263 }
  ]
}
```

### 5.3 `GET /api/risk-free-rate` → `{ rate: number, asOf: string, source: "FRED" | "FALLBACK" }`

Returns the annualized 3-month T-bill yield.

```json
{ "rate": 0.0523, "asOf": "2024-11-20T00:00:00Z", "source": "FRED" }
```

### 5.4 `POST /api/optimize` — body `OptimizationRequest` → `OptimizationResult`

End-to-end: fetch prices → compute metrics → solve ORP → apply utility max → build CAL & frontier.

Example request:

```json
{
  "tickers": ["AAPL", "MSFT", "NVDA", "JPM", "XOM"],
  "riskProfile": { "riskAversion": 3, "targetReturn": 0.15 },
  "returnFrequency": "daily",
  "lookbackYears": 5,
  "allowShort": true,
  "allowLeverage": true,
  "frontierResolution": 40
}
```

Example response (shape — values illustrative):

```json
{
  "requestId": "opt_2e9a...",
  "asOf": "2024-11-21T21:04:12Z",
  "riskFreeRate": 0.0523,
  "market": { "expectedReturn": 0.105, "stdDev": 0.185, "variance": 0.034225 },
  "stocks": [
    { "ticker": "AAPL", "expectedReturn": 0.21, "stdDev": 0.27, "beta": 1.22, "alpha": 0.041, "firmSpecificVar": 0.034, "nObservations": 1258 }
  ],
  "covariance": { "tickers": ["AAPL","MSFT","NVDA","JPM","XOM"], "matrix": [[0.0729, 0.054, 0.061, 0.029, 0.018], [/* ... */]] },
  "orp": {
    "weights": { "AAPL": 0.28, "MSFT": 0.22, "NVDA": 0.31, "JPM": 0.15, "XOM": 0.04 },
    "expectedReturn": 0.182, "stdDev": 0.214, "variance": 0.045796, "sharpe": 0.607
  },
  "complete": {
    "yStar": 0.95, "weightRiskFree": 0.05,
    "weights": { "AAPL": 0.266, "MSFT": 0.209, "NVDA": 0.2945, "JPM": 0.1425, "XOM": 0.038 },
    "expectedReturn": 0.1754, "stdDev": 0.2033, "leverageUsed": false
  },
  "frontierPoints": [{ "stdDev": 0.16, "expectedReturn": 0.12 }],
  "calPoints": [{ "stdDev": 0.0, "expectedReturn": 0.0523, "y": 0.0 }, { "stdDev": 0.214, "expectedReturn": 0.182, "y": 1.0 }],
  "warnings": []
}
```

### 5.5 `POST /api/backtest` — body `BacktestRequest` → `BacktestResult`

Replays the optimizer over historical windows with the chosen rebalance cadence.

### 5.6 Portfolios CRUD

- `GET    /api/portfolios` → `SavedPortfolio[]`
- `POST   /api/portfolios` — body `Portfolio` → `SavedPortfolio`
- `GET    /api/portfolios/{id}` → `SavedPortfolio`
- `PUT    /api/portfolios/{id}` — body `Portfolio` → `SavedPortfolio`
- `DELETE /api/portfolios/{id}` → `204 No Content`

### 5.7 `POST /api/portfolios/{id}/drift` — body `{ currentWeights: Record<Ticker, number> }` → `DriftReport`

Client supplies their current holdings; server compares to the portfolio's last target weights.

### 5.8 `POST /api/compare` — body `CompareRequest` → `{ results: Record<string, OptimizationResult> }`

Runs `/optimize` for each saved portfolio and returns them keyed by `id`.

### 5.9 `POST /api/chat` — body `ChatRequest` → `ChatResponse`

Hybrid rule + LLM chat. When `mode="auto"` (default), the rule-based intent classifier answers first and the OpenAI LLM is used only on intent miss (and only when `OPENAI_API_KEY` is set). `mode="rule"` locks to the rule engine. `mode="llm"` forces the LLM path and returns `503 LLM_UNAVAILABLE` when the key is unset. If `sessionId` is provided, the turn is appended to the session log via §5.11.

### 5.11 Chat sessions

Browser-owned chat history, persisted to the backend SQLite store at `CACHE_DB_PATH`. The `sessionId` is generated client-side (UUID v4) and stored in `localStorage`. Sessions are independent of saved portfolios — the forward-compatible `portfolioId` FK is reserved for Phase 3C.

- `GET    /api/chat/sessions/{sessionId}` → `ChatSessionResponse`. Returns an empty message list for unknown session IDs (lazy creation on first POST).
- `POST   /api/chat/sessions/{sessionId}/messages` — body `ChatRequest` → `ChatResponse`. Persists the final user turn plus the assistant reply (with `source` and `citations`).
- `DELETE /api/chat/sessions/{sessionId}` → `204 No Content`.

### 5.12 `POST /api/export/pdf` — body `{ result: OptimizationResult }` → `application/pdf` binary

Returns the rendered report as a PDF stream. `Content-Disposition: attachment; filename="portfolio-<requestId>.pdf"`.

### 5.13 `POST /api/analytics/performance` — body `AnalyticsPerformanceRequest` → `AnalyticsPerformanceResult`

Treynor, portfolio Jensen (SIM) alpha, **SIM variance decomposition** for the **ORP** weights supplied, **3/5/10-year** arithmetic and geometric *mean monthly* simple returns, and per-ticker Fama–French 3 (bundled factors). Does not run the Markowitz optimizer.

### 5.14 `POST /api/valuation` — body `ValuationRequest` → `ValuationResult`

FCFF, FCFE, DDM (Gordon and optional two-stage) per ticker; pulls fundamentals via **Yahoo Finance** (`yfinance`) first, then **Alpha Vantage** (`INCOME_STATEMENT`, `BALANCE_SHEET`, `CASH_FLOW`, `OVERVIEW`) when the key is set and Yahoo cannot supply a complete bundle. Response `dataSource` is `yahoo`, `alpha-vantage`, or `mixed` when tickers used different providers. `INVALID_VALUATION` is returned for invalid DDM or discount-rate assumptions (e.g. `g >= k`).

---

## 6. Wire-format rules

1. **Pydantic config** (backend): every model uses
  ```python
   model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, ser_json_inf_nan="null")
  ```
   so request and response JSON is always `camelCase`, while Python code reads `snake_case`.
2. **TypeScript types** live in `frontend/src/types/contracts.ts`. They are the *only* place these types are declared on the frontend — components import from there.
3. **Numbers**: never send `NaN` or `Infinity` over the wire. Any non-finite float at serialization time is an error (`ErrorCode.INTERNAL`).
4. **Lists of weights**: `ORP.weights` and `CompletePortfolio.weights` must include every ticker in the request, even if the weight is `0.0` (absence is ambiguous).
5. **Versioning**: this is v1. A breaking change to any shape requires bumping an HTTP header `X-API-Version` and updating both SPEC.md and this file in the same PR.

