/**
 * TypeScript mirror of `backend/quant/types.py` and `docs/CONTRACTS.md` §3.
 *
 * Field names are camelCase — matching the wire format (the backend's
 * Pydantic layer emits camelCase via `alias_generator=to_camel`). The Python
 * source of truth uses snake_case internally; the two representations are
 * equivalent on the wire.
 */

export type Ticker = string;

export const ReturnFrequency = {
  Daily: "daily",
  Weekly: "weekly",
  Monthly: "monthly",
} as const;

export type ReturnFrequency = (typeof ReturnFrequency)[keyof typeof ReturnFrequency];

export interface StockMetrics {
  ticker: Ticker;
  expectedReturn: number;
  stdDev: number;
  beta: number;
  alpha: number;
  firmSpecificVar: number;
  nObservations: number;
}

export interface MarketMetrics {
  expectedReturn: number;
  stdDev: number;
  variance: number;
}

export interface CovarianceMatrix {
  tickers: Ticker[];
  matrix: number[][];
}

export interface RiskProfile {
  riskAversion: number;
  targetReturn?: number;
}

export interface FrontierPoint {
  stdDev: number;
  expectedReturn: number;
}

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
  orp: ORP;
  complete: CompletePortfolio;
  frontierPoints: FrontierPoint[];
  calPoints: CALPoint[];
  warnings: string[];
}
