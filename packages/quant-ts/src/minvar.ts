/**
 * Global minimum-variance portfolio — TypeScript mirror of
 * `backend/quant/minvar.py`.
 *
 * - Unconstrained: `w = Σ⁻¹𝟏 / (𝟏ᵀΣ⁻¹𝟏)`.
 * - Long-only: active-set iteration (same structure as tangency).
 */

import { OptimizerInfeasibleError } from "./errors.js";
import { dot, ensurePsdCovariance, matVec, solve, sumVec } from "./linalg.js";
import type { ORP } from "./types.js";

export const SUM_TOL = 1e-9;

function mvpUnconstrained(cov: number[][]): number[] {
  const n = cov.length;
  const ones = new Array<number>(n).fill(1);
  const z = solve(cov, ones);
  const s = sumVec(z);
  if (!Number.isFinite(s) || Math.abs(s) < 1e-14) {
    throw new OptimizerInfeasibleError(
      "unconstrained MVP normalization is degenerate",
      { sum: s },
    );
  }
  return z.map((v) => v / s);
}

function subMatrix(matrix: readonly (readonly number[])[], idx: readonly number[]): number[][] {
  return idx.map((i) => idx.map((j) => ((matrix[i] as readonly number[])[j] as number)));
}

function mvpLongOnly(cov: number[][]): number[] {
  const n = cov.length;
  let active = Array.from({ length: n }, (_, i) => i);

  for (let iter = 0; iter < n + 1; iter += 1) {
    if (active.length === 0) {
      throw new OptimizerInfeasibleError("long-only MVP active set became empty", {});
    }
    const subCov = subMatrix(cov, active);
    const subW = mvpUnconstrained(subCov);

    const minIdx = subW.reduce((iMin, v, i) => (v < (subW[iMin] as number) ? i : iMin), 0);
    const minVal = subW[minIdx] as number;
    if (minVal >= -1e-12) {
      const full = new Array<number>(n).fill(0);
      for (let k = 0; k < active.length; k += 1) {
        full[active[k] as number] = Math.max(subW[k] as number, 0);
      }
      const s = sumVec(full);
      if (s <= SUM_TOL) {
        throw new OptimizerInfeasibleError("long-only MVP produced zero weights", { sum: s });
      }
      return full.map((v) => v / s);
    }
    active = active.filter((_, k) => k !== minIdx);
  }
  throw new OptimizerInfeasibleError(
    "long-only MVP failed to converge within n iterations",
    { n },
  );
}

export interface MinimumVarianceInput {
  tickers: readonly string[];
  expectedReturns: readonly number[];
  covariance: number[][];
  riskFreeRate: number;
  allowShort: boolean;
  warnings?: string[];
}

export function minimumVariancePortfolio(input: MinimumVarianceInput): ORP {
  const { tickers, expectedReturns, covariance, riskFreeRate, allowShort, warnings } = input;
  if (expectedReturns.length !== tickers.length) {
    throw new Error(
      `tickers length ${tickers.length} != expectedReturns length ${expectedReturns.length}`,
    );
  }
  if (covariance.length !== tickers.length) {
    throw new Error(`covariance must be ${tickers.length}x${tickers.length}`);
  }
  const cov = ensurePsdCovariance(covariance, warnings);

  let w = allowShort ? mvpUnconstrained(cov) : mvpLongOnly(cov);

  const s = sumVec(w);
  if (Math.abs(s - 1) > SUM_TOL) w = w.map((x) => x / s);

  const expectedReturn = dot(expectedReturns, w);
  const variance = dot(w, matVec(cov, w));
  if (variance <= 0) {
    throw new OptimizerInfeasibleError("MVP variance came out non-positive", {
      variance,
    });
  }
  const stdDev = Math.sqrt(variance);
  const sharpe = (expectedReturn - riskFreeRate) / stdDev;

  const weights: Record<string, number> = {};
  for (let i = 0; i < tickers.length; i += 1) {
    weights[tickers[i] as string] = w[i] as number;
  }
  return { weights, expectedReturn, stdDev, variance, sharpe };
}
