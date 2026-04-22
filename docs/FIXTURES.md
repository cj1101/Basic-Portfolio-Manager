# Fixtures — Golden Datasets (FIXTURES.md)

> **This is a Phase 0 artifact.** Every downstream math and data agent MUST include at least one test using **Dataset A** (synthetic, closed-form) and every data/integration agent MUST include at least one test using **Dataset B** (real tickers, snapshot-frozen). The numerical outputs below are the arbiter of correctness — if your code disagrees, your code is wrong (or, rarely, this file is wrong and needs a PR).
>
> **Hand-computed**: all Dataset A outputs are derived via exact arithmetic from the closed-form tangency-portfolio formula. See the "Derivation" section at the end for the math trace.

Contents:

1. [Dataset A — Synthetic textbook (closed-form)](#1-dataset-a--synthetic-textbook)
2. [Dataset B — Real-world 5 tickers (snapshot-frozen)](#2-dataset-b--real-world-5-tickers)
3. [Frontend sample — `OptimizationResult` ready to import](#3-frontend-sample--optimizationresult)
4. [Tolerance rules for assertions](#4-tolerance-rules-for-assertions)
5. [Derivations (math trace for Dataset A)](#5-derivations-math-trace-for-dataset-a)

---

## 1. Dataset A — Synthetic textbook

**Purpose**: the covariance matrix is diagonal (zero correlations) so every quantity has a closed-form solution. Any math regression is caught instantly.

### Inputs

```json
{
  "datasetId": "A",
  "riskFreeRate": 0.04,
  "stocks": [
    { "ticker": "S1", "expectedReturn": 0.10, "stdDev": 0.15, "beta": 0.80, "alpha": 0.012, "firmSpecificVar": 0.01 },
    { "ticker": "S2", "expectedReturn": 0.13, "stdDev": 0.20, "beta": 1.10, "alpha": 0.024, "firmSpecificVar": 0.02 },
    { "ticker": "S3", "expectedReturn": 0.16, "stdDev": 0.30, "beta": 1.50, "alpha": 0.030, "firmSpecificVar": 0.05 }
  ],
  "correlation": [
    [1.0, 0.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0]
  ]
}
```

The covariance matrix derived from the above (σᵢ · σⱼ · ρᵢⱼ, then `σᵢ²` on the diagonal) is:

```json
{
  "tickers": ["S1", "S2", "S3"],
  "matrix": [
    [0.0225, 0.0000, 0.0000],
    [0.0000, 0.0400, 0.0000],
    [0.0000, 0.0000, 0.0900]
  ]
}
```

### Expected — Optimal Risky Portfolio (full-MPT tangency, shorts allowed)

Computed from the unconstrained tangency formula `w* ∝ Σ⁻¹(μ − rᶠ·𝟏)`, normalized so weights sum to 1.

```json
{
  "orp": {
    "weights": { "S1": 0.426667, "S2": 0.360000, "S3": 0.213333 },
    "expectedReturn": 0.123600,
    "stdDev": 0.115655,
    "variance": 0.013376,
    "sharpe": 0.722842
  }
}
```

Exact rational weights (for reference): `w = [32/75, 9/25, 16/75]`. `Sharpe² = (μ−rᶠ)ᵀΣ⁻¹(μ−rᶠ) = 0.5225`.

### Expected — Global Minimum-Variance Portfolio (fully invested, long/short)

Derived from `w_mv ∝ Σ⁻¹·𝟏`. Included as a sanity check for any `minimum_variance_portfolio` helper.

```json
{
  "minimumVariance": {
    "weights": { "S1": 0.551724, "S2": 0.310345, "S3": 0.137931 },
    "expectedReturn": 0.117586,
    "stdDev": 0.111419,
    "variance": 0.012414
  }
}
```

Exact rationals: `w = [16/29, 9/29, 4/29]`.

### Expected — Complete portfolios along the CAL

`y* = (E(r_ORP) − rᶠ) / (A · σ²_ORP)` with the ORP numbers above.

#### Case A-LEV (risk aversion `A = 4`): leverage used

```json
{
  "riskProfile": { "riskAversion": 4 },
  "complete": {
    "yStar": 1.562500,
    "weightRiskFree": -0.562500,
    "weights": { "S1": 0.666667, "S2": 0.562500, "S3": 0.333333 },
    "expectedReturn": 0.170625,
    "stdDev": 0.180711,
    "leverageUsed": true
  }
}
```

#### Case A-NOLEV (risk aversion `A = 8`): no leverage

```json
{
  "riskProfile": { "riskAversion": 8 },
  "complete": {
    "yStar": 0.781250,
    "weightRiskFree": 0.218750,
    "weights": { "S1": 0.333333, "S2": 0.281250, "S3": 0.166667 },
    "expectedReturn": 0.105313,
    "stdDev": 0.090356,
    "leverageUsed": false
  }
}
```

### Expected — CAPM & Single-Index Model single-stock

Inputs: `rᶠ = 0.04`, `E(r_M) = 0.10`, `σ_M = 0.18` (⇒ `σ²_M = 0.0324`), test stock `β = 1.2`, `α = 0.02`, `σ²(e) = 0.01`.

```json
{
  "capm": {
    "requiredReturn": 0.112,
    "totalExpectedReturn": 0.132,
    "systematicVariance": 0.046656,
    "totalVariance": 0.056656,
    "stdDev": 0.238025
  }
}
```

- `r_CAPM = rᶠ + β(E(r_M) − rᶠ) = 0.04 + 1.2 × 0.06 = 0.112`
- `E(r) = r_CAPM + α = 0.132`
- `Var = β²σ²_M + σ²(e) = 1.44 × 0.0324 + 0.01 = 0.056656`
- `σ = √0.056656 ≈ 0.238025`

---

## 2. Dataset B — Real-world 5 tickers

**Purpose**: end-to-end integration test of the data layer and the full pipeline against live Alpha Vantage data. Values will have small realized drift between AV refreshes, so assertions use the **tolerance table** in section 4, not exact match.

### Inputs

```json
{
  "datasetId": "B",
  "tickers": ["AAPL", "MSFT", "NVDA", "JPM", "XOM"],
  "marketBenchmark": "SPY",
  "returnFrequency": "daily",
  "lookbackYears": 5,
  "asOfPolicy": "last-trading-day-on-or-before(2024-11-21)",
  "riskProfile": { "riskAversion": 3, "targetReturn": 0.15 },
  "allowShort": true,
  "allowLeverage": true
}
```

### Snapshot integrity

Agent 1A must produce, and commit to `backend/data/snapshots/dataset_b.json`, a normalized JSON of the bars fetched for each ticker across the 5-year window above. The SHA-256 of this file (sorted-key canonical JSON, LF newlines, no trailing newline) is recorded by the data agent's test and locked via a fixture.

**Canonical shape** (captured by `backend/tests/data/test_dataset_b.py`):

```json
{
  "datasetId": "B",
  "asOfPolicy": "last-trading-day-on-or-before(2024-11-21)",
  "windowEnd": "YYYY-MM-DD",
  "lookbackYears": 5,
  "tickers": ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "SPY"],
  "provider": "ALPHA_VANTAGE",
  "series": {
    "AAPL": { "count": 1258, "bars": [{ "date": "YYYY-MM-DD", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0 }, "…"] },
    "…": "…"
  }
}
```

**Provider-stability**: the test asserts every ticker resolved through the same provider — so the locked hash is **not** a mixture of Alpha Vantage and Yahoo bars. If the primary provider is unreachable, re-run the test when it comes back; do not commit a snapshot that mixes providers.

**AV-only**: the snapshot lock is Alpha Vantage-only. AV returns prices as fixed-precision text (`"192.5300"`), so parsing them to float and writing them back is exact. Yahoo's `yfinance` pipeline internally uses float32 and auto-adjust multipliers that jitter by ~1e-5 between fetches — enough to flip a SHA-256 at any rounding precision that preserves real information. With `ALPHA_VANTAGE_API_KEY` unset the test skips with an informational message instead of producing a noisy Yahoo-based lock. Yahoo remains the runtime fallback for `GET /api/historical`; only the snapshot lock is restricted.

```json
{
  "snapshotFile": "backend/data/snapshots/dataset_b.json",
  "hashAlgorithm": "sha256",
  "hashPlaceholder": "<to-be-set-by-agent-1A-in-its-first-PR>"
}
```

> The hash is intentionally blank: on first successful live-gated run (`RUN_LIVE_TESTS=1` with `ALPHA_VANTAGE_API_KEY` set), the test writes the snapshot, computes the SHA-256, and patches the placeholder in this file in place. Subsequent runs re-fetch from AV and assert byte-exact hash equality — any drift fails the build loudly. A feature, not a bug.

### Expected — metrics (soft bounds, to 3 dp)

These are expected ranges based on the 5-year daily AV history ending on the as-of date above. Any individual metric landing outside its bound flags either a data issue or a math issue.

```json
{
  "marketMetrics": {
    "expectedReturn": [0.09, 0.14],
    "stdDev":         [0.16, 0.22]
  },
  "stockMetrics": {
    "AAPL": { "expectedReturn": [0.18, 0.30], "stdDev": [0.22, 0.32], "beta": [1.05, 1.40], "alpha": [0.02, 0.12], "firmSpecificVar": [0.020, 0.060] },
    "MSFT": { "expectedReturn": [0.18, 0.30], "stdDev": [0.22, 0.32], "beta": [0.95, 1.30], "alpha": [0.03, 0.13], "firmSpecificVar": [0.020, 0.060] },
    "NVDA": { "expectedReturn": [0.50, 1.10], "stdDev": [0.40, 0.65], "beta": [1.50, 2.10], "alpha": [0.30, 0.90], "firmSpecificVar": [0.100, 0.250] },
    "JPM":  { "expectedReturn": [0.08, 0.22], "stdDev": [0.20, 0.32], "beta": [0.95, 1.35], "alpha": [-0.05, 0.08], "firmSpecificVar": [0.020, 0.060] },
    "XOM":  { "expectedReturn": [0.05, 0.22], "stdDev": [0.24, 0.40], "beta": [0.70, 1.20], "alpha": [-0.03, 0.10], "firmSpecificVar": [0.040, 0.110] }
  }
}
```

### Expected — ORP (direction, not exact)

Shorts are permitted; NVDA and MSFT should dominate the weights. XOM often appears negative (shorted) due to low alpha relative to its variance contribution.

```json
{
  "orpExpectations": {
    "weights": {
      "AAPL": [0.05, 0.35],
      "MSFT": [0.10, 0.45],
      "NVDA": [0.15, 0.50],
      "JPM":  [-0.20, 0.25],
      "XOM":  [-0.35, 0.10]
    },
    "sharpe": [0.70, 1.40],
    "sumOfWeights": 1.0,
    "weightsSumTolerance": 1e-6
  }
}
```

### Expected — Complete portfolio (`A = 3`)

```json
{
  "completeExpectations": {
    "yStar":          [0.60, 1.80],
    "leverageUsed":   "either",
    "expectedReturn": [0.10, 0.30]
  }
}
```

---

## 3. Frontend sample — `OptimizationResult`

Agent 1B imports this constant directly as `import sample from "./fixtures/optimizationResultSample"` — it is the ONLY data source for the Phase 1 frontend. Values are **illustrative realistic** (not re-derived from Dataset B) so the UI can build without waiting on the backend.

```json
{
  "requestId": "opt_sample_phase0",
  "asOf": "2024-11-21T21:04:12Z",
  "riskFreeRate": 0.0523,
  "market": {
    "expectedReturn": 0.1050,
    "stdDev": 0.1850,
    "variance": 0.034225
  },
  "stocks": [
    { "ticker": "AAPL", "expectedReturn": 0.22, "stdDev": 0.27, "beta": 1.22, "alpha": 0.045, "firmSpecificVar": 0.0340, "nObservations": 1258 },
    { "ticker": "MSFT", "expectedReturn": 0.23, "stdDev": 0.26, "beta": 1.14, "alpha": 0.068, "firmSpecificVar": 0.0310, "nObservations": 1258 },
    { "ticker": "NVDA", "expectedReturn": 0.76, "stdDev": 0.52, "beta": 1.80, "alpha": 0.570, "firmSpecificVar": 0.1800, "nObservations": 1258 },
    { "ticker": "JPM",  "expectedReturn": 0.14, "stdDev": 0.26, "beta": 1.18, "alpha": 0.020, "firmSpecificVar": 0.0330, "nObservations": 1258 },
    { "ticker": "XOM",  "expectedReturn": 0.12, "stdDev": 0.32, "beta": 0.92, "alpha": 0.018, "firmSpecificVar": 0.0720, "nObservations": 1258 }
  ],
  "covariance": {
    "tickers": ["AAPL", "MSFT", "NVDA", "JPM", "XOM"],
    "matrix": [
      [0.0729, 0.0510, 0.0690, 0.0330, 0.0200],
      [0.0510, 0.0676, 0.0630, 0.0300, 0.0180],
      [0.0690, 0.0630, 0.2704, 0.0420, 0.0250],
      [0.0330, 0.0300, 0.0420, 0.0676, 0.0220],
      [0.0200, 0.0180, 0.0250, 0.0220, 0.1024]
    ]
  },
  "correlation": {
    "tickers": ["AAPL", "MSFT", "NVDA", "JPM", "XOM"],
    "matrix": [
      [1.0, 0.726496, 0.491453, 0.470085, 0.231481],
      [0.726496, 1.0, 0.465976, 0.443787, 0.216346],
      [0.491453, 0.465976, 1.0, 0.310651, 0.150240],
      [0.470085, 0.443787, 0.310651, 1.0, 0.264423],
      [0.231481, 0.216346, 0.150240, 0.264423, 1.0]
    ]
  },
  "orp": {
    "weights": { "AAPL": 0.18, "MSFT": 0.24, "NVDA": 0.31, "JPM": 0.15, "XOM": 0.12 },
    "expectedReturn": 0.2940,
    "stdDev": 0.2510,
    "variance": 0.063001,
    "sharpe": 0.9630
  },
  "complete": {
    "yStar": 0.95,
    "weightRiskFree": 0.05,
    "weights": { "AAPL": 0.1710, "MSFT": 0.2280, "NVDA": 0.2945, "JPM": 0.1425, "XOM": 0.1140 },
    "expectedReturn": 0.2809,
    "stdDev": 0.2385,
    "leverageUsed": false
  },
  "frontierPoints": [
    { "stdDev": 0.1800, "expectedReturn": 0.1400 },
    { "stdDev": 0.1950, "expectedReturn": 0.1800 },
    { "stdDev": 0.2100, "expectedReturn": 0.2150 },
    { "stdDev": 0.2300, "expectedReturn": 0.2500 },
    { "stdDev": 0.2510, "expectedReturn": 0.2940 },
    { "stdDev": 0.2800, "expectedReturn": 0.3200 },
    { "stdDev": 0.3200, "expectedReturn": 0.3350 }
  ],
  "calPoints": [
    { "stdDev": 0.0000, "expectedReturn": 0.0523, "y": 0.0 },
    { "stdDev": 0.1255, "expectedReturn": 0.1732, "y": 0.5 },
    { "stdDev": 0.2510, "expectedReturn": 0.2940, "y": 1.0 },
    { "stdDev": 0.3765, "expectedReturn": 0.4148, "y": 1.5 }
  ],
  "warnings": []
}
```

---

## 4. Tolerance rules for assertions

| Assertion type | Tolerance | Rationale |
|---|---|---|
| Dataset A — scalar weight, E(r), σ, variance, Sharpe | `abs(actual − expected) ≤ 1e-6` | Closed-form, should be exact to float precision |
| Dataset A — sum of weights | `abs(sum − 1) ≤ 1e-9` | No reason to drift |
| Dataset B — scalar metric | Inside the `[lo, hi]` soft bound | AV data refreshes move values by up to ~1 bp over time |
| Dataset B — weight direction (sign) | Must match expected sign bucket | Weights flipping sign on a rerun means something is wrong |
| Covariance matrix — symmetry | `max |Σ − Σᵀ| ≤ 1e-10` | Always symmetric by construction |
| Covariance matrix — PSD | Minimum eigenvalue `≥ −1e-8` (then projected via nearestPD if needed) | Numerical drift allowed; negative-eigen outside tolerance is a bug |
| Snapshot hash (Dataset B) | Byte-exact | Any drift = test failure |

---

## 5. Derivations (math trace for Dataset A)

### 5.1 Covariance matrix

Since `ρᵢⱼ = 0` for `i ≠ j`, `Σᵢⱼ = σᵢ·σⱼ·ρᵢⱼ = 0` off-diagonal and `Σᵢᵢ = σᵢ²`.

`Σ = diag(0.15², 0.20², 0.30²) = diag(0.0225, 0.04, 0.09)`.

### 5.2 Tangency (ORP)

Unconstrained tangency: `w* ∝ Σ⁻¹(μ − rᶠ·𝟏)`, then normalize `w = w* / Σᵢ wᵢ*`.

- `μ − rᶠ·𝟏 = [0.06, 0.09, 0.12]`
- `Σ⁻¹(μ − rᶠ·𝟏) = [0.06/0.0225, 0.09/0.04, 0.12/0.09] = [8/3, 9/4, 4/3]`
- Sum of entries `= 8/3 + 9/4 + 4/3 = 32/12 + 27/12 + 16/12 = 75/12 = 25/4`
- Normalized weights: `w = [(8/3)/(25/4), (9/4)/(25/4), (4/3)/(25/4)] = [32/75, 9/25, 16/75]`

### 5.3 ORP moments

- `E(r_ORP) = (32/75)(0.10) + (9/25)(0.13) + (16/75)(0.16) = 9.27/75 = 0.1236`
- `Var = w²ᵀ·diag(Σ) = (32/75)²(0.0225) + (9/25)²(0.04) + (16/75)²(0.09) = 0.013376`
- `σ = √0.013376 ≈ 0.115655`
- `Sharpe² = (μ−rᶠ)ᵀΣ⁻¹(μ−rᶠ) = 0.06·(8/3) + 0.09·(9/4) + 0.12·(4/3) = 0.16 + 0.2025 + 0.16 = 0.5225`
- `Sharpe = √0.5225 ≈ 0.722842`

### 5.4 Global minimum variance

- `w_mv ∝ Σ⁻¹·𝟏 = [1/0.0225, 1/0.04, 1/0.09] = [400/9, 25, 100/9]`
- Sum `= 725/9`. `w_mv = [16/29, 9/29, 4/29]`
- `E(r_mv) = (16/29)(0.10) + (9/29)(0.13) + (4/29)(0.16) = 3.41/29 ≈ 0.117586`
- `Var_mv = (256·0.0225 + 81·0.04 + 16·0.09)/29² = 10.44/841 ≈ 0.012414`
- `σ_mv ≈ 0.111419`

### 5.5 Capital-Allocation blending

`y* = (E(r_ORP) − rᶠ) / (A·σ²_ORP) = 0.0836 / (A · 0.013376)`.

| A | y\* exact | y\*·σ_ORP (σ of complete) | E(r_complete) = rᶠ + y\*·0.0836 |
|---|---|---|---|
| 4 | 0.0836 / 0.053504 = **1.562500** | 1.5625 × 0.115655 = **0.180711** | 0.04 + 0.130625 = **0.170625** |
| 8 | 0.0836 / 0.107008 = **0.781250** | 0.781250 × 0.115655 = **0.090356** | 0.04 + 0.0653125 = **0.105313** |

Complete weights are `y* · w_ORP` for risky assets and `(1 − y*)` in the risk-free asset:

- `A = 4`: `1.5625 · [32/75, 9/25, 16/75] = [2/3, 9/16, 1/3]` exactly ⇒ `[0.666667, 0.562500, 0.333333]`
- `A = 8`: `0.78125 · [32/75, 9/25, 16/75] = [1/3, 9/32, 1/6]` exactly ⇒ `[0.333333, 0.281250, 0.166667]`

### 5.6 CAPM & SIM single-stock

Given `rᶠ = 0.04`, `E(r_M) = 0.10`, `σ_M = 0.18`, test stock `(β, α, σ²(e)) = (1.2, 0.02, 0.01)`:

- `r_CAPM = 0.04 + 1.2·(0.10 − 0.04) = 0.112`
- `E(r) = r_CAPM + α = 0.132`
- `β²·σ²_M = 1.44·0.0324 = 0.046656`
- `Var = 0.046656 + 0.01 = 0.056656`
- `σ = √0.056656 ≈ 0.238025`
