import type { OptimizationResult } from "@/types/contracts";

/**
 * Phase 1 Agent C is bound exclusively to this constant.
 *
 * Values transcribed verbatim from `docs/FIXTURES.md` §3 "Frontend sample".
 * This is illustrative-realistic data, NOT re-derived from Dataset B.
 *
 * Typing it as `OptimizationResult` (not `as const`) gives the full
 * contract type everywhere it is consumed — mutating it mid-session is
 * explicitly permitted for Phase 1 (see `portfolioContext.tsx`), which
 * re-derives a `CompletePortfolio` from this immutable ORP + live
 * riskProfile using the formulas in `lib/completePortfolio.ts`.
 */
export const optimizationResultSample: OptimizationResult = {
  requestId: "opt_sample_phase0",
  asOf: "2024-11-21T21:04:12Z",
  riskFreeRate: 0.0523,
  market: {
    expectedReturn: 0.105,
    stdDev: 0.185,
    variance: 0.034225,
  },
  stocks: [
    {
      ticker: "AAPL",
      expectedReturn: 0.22,
      stdDev: 0.27,
      beta: 1.22,
      alpha: 0.045,
      firmSpecificVar: 0.034,
      nObservations: 1258,
    },
    {
      ticker: "MSFT",
      expectedReturn: 0.23,
      stdDev: 0.26,
      beta: 1.14,
      alpha: 0.068,
      firmSpecificVar: 0.031,
      nObservations: 1258,
    },
    {
      ticker: "NVDA",
      expectedReturn: 0.76,
      stdDev: 0.52,
      beta: 1.8,
      alpha: 0.57,
      firmSpecificVar: 0.18,
      nObservations: 1258,
    },
    {
      ticker: "JPM",
      expectedReturn: 0.14,
      stdDev: 0.26,
      beta: 1.18,
      alpha: 0.02,
      firmSpecificVar: 0.033,
      nObservations: 1258,
    },
    {
      ticker: "XOM",
      expectedReturn: 0.12,
      stdDev: 0.32,
      beta: 0.92,
      alpha: 0.018,
      firmSpecificVar: 0.072,
      nObservations: 1258,
    },
  ],
  covariance: {
    tickers: ["AAPL", "MSFT", "NVDA", "JPM", "XOM"],
    matrix: [
      [0.0729, 0.051, 0.069, 0.033, 0.02],
      [0.051, 0.0676, 0.063, 0.03, 0.018],
      [0.069, 0.063, 0.2704, 0.042, 0.025],
      [0.033, 0.03, 0.042, 0.0676, 0.022],
      [0.02, 0.018, 0.025, 0.022, 0.1024],
    ],
  },
  orp: {
    weights: {
      AAPL: 0.18,
      MSFT: 0.24,
      NVDA: 0.31,
      JPM: 0.15,
      XOM: 0.12,
    },
    expectedReturn: 0.294,
    stdDev: 0.251,
    variance: 0.063001,
    sharpe: 0.963,
  },
  complete: {
    yStar: 0.95,
    weightRiskFree: 0.05,
    weights: {
      AAPL: 0.171,
      MSFT: 0.228,
      NVDA: 0.2945,
      JPM: 0.1425,
      XOM: 0.114,
    },
    expectedReturn: 0.2809,
    stdDev: 0.2385,
    leverageUsed: false,
  },
  frontierPoints: [
    { stdDev: 0.18, expectedReturn: 0.14 },
    { stdDev: 0.195, expectedReturn: 0.18 },
    { stdDev: 0.21, expectedReturn: 0.215 },
    { stdDev: 0.23, expectedReturn: 0.25 },
    { stdDev: 0.251, expectedReturn: 0.294 },
    { stdDev: 0.28, expectedReturn: 0.32 },
    { stdDev: 0.32, expectedReturn: 0.335 },
  ],
  calPoints: [
    { stdDev: 0.0, expectedReturn: 0.0523, y: 0.0 },
    { stdDev: 0.1255, expectedReturn: 0.1732, y: 0.5 },
    { stdDev: 0.251, expectedReturn: 0.294, y: 1.0 },
    { stdDev: 0.3765, expectedReturn: 0.4148, y: 1.5 },
  ],
  warnings: [],
};

export default optimizationResultSample;
