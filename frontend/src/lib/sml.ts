import type { MarketMetrics, StockMetrics } from "@/types/contracts";

/**
 * Security Market Line helpers (CAPM display math).
 *
 *   r_CAPM(β) = r_f + β · (E(r_M) - r_f)
 *   α        = E(r) - r_CAPM(β)      (historical residual, from StockMetrics)
 */

export interface SMLPoint {
  beta: number;
  expectedReturn: number;
}

export function smlLine(
  market: MarketMetrics,
  riskFreeRate: number,
  betaMax = 2.5,
  steps = 2,
): SMLPoint[] {
  const excess = market.expectedReturn - riskFreeRate;
  return Array.from({ length: steps + 1 }, (_, i) => {
    const beta = (betaMax * i) / steps;
    return {
      beta,
      expectedReturn: riskFreeRate + beta * excess,
    };
  });
}

export function capmRequiredReturn(
  market: MarketMetrics,
  riskFreeRate: number,
  beta: number,
): number {
  return riskFreeRate + beta * (market.expectedReturn - riskFreeRate);
}

export interface StockSMLPoint {
  ticker: string;
  beta: number;
  expectedReturn: number;
  alpha: number;
}

export function stocksForSML(
  stocks: StockMetrics[],
  market: MarketMetrics,
  riskFreeRate: number,
): StockSMLPoint[] {
  return stocks.map((s) => ({
    ticker: s.ticker,
    beta: s.beta,
    expectedReturn: s.expectedReturn,
    alpha: s.expectedReturn - capmRequiredReturn(market, riskFreeRate, s.beta),
  }));
}
