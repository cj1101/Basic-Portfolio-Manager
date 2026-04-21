/**
 * Markowitz Optimal Risky Portfolio (tangency) — `.cursor/rules/quant.mdc` §3.
 *
 * Unconstrained (`allowShort: true`): closed form,
 * `w* ∝ Σ⁻¹(μ − rᶠ·𝟏)` normalized to sum to 1.
 *
 * Long-only (`allowShort: false`): active-set iteration. Start with all
 * assets, solve unconstrained on the active subset; if any weight comes out
 * negative, drop the most-negative asset and repeat. Terminates because the
 * active set strictly shrinks on each iteration. This is exact whenever the
 * unconstrained solution on every candidate subset has non-negative weights
 * — which includes the Dataset A textbook case (diagonal Σ, positive excess
 * returns) and most real-world inputs.
 */

import { OptimizerInfeasibleError } from "./errors.js";
import { dot, ensurePsdCovariance, matVec, solve, sumVec } from "./linalg.js";
import type { ORP } from "./types.js";

export const SUM_TOL = 1e-9;

function tangencyUnconstrained(
  mu: readonly number[],
  cov: number[][],
  rf: number,
): number[] {
  const excess = mu.map((m) => m - rf);
  const z = solve(cov, excess);
  const s = sumVec(z);
  if (!Number.isFinite(s) || Math.abs(s) < 1e-14) {
    throw new OptimizerInfeasibleError(
      "tangency normalization is degenerate; Σ⁻¹(μ − rᶠ𝟏) sums to ~0",
      { sum: s },
    );
  }
  return z.map((v) => v / s);
}

function subMatrix(matrix: readonly (readonly number[])[], idx: readonly number[]): number[][] {
  return idx.map((i) => idx.map((j) => ((matrix[i] as readonly number[])[j] as number)));
}

function subVector(vec: readonly number[], idx: readonly number[]): number[] {
  return idx.map((i) => vec[i] as number);
}

function tangencyLongOnly(
  mu: readonly number[],
  cov: number[][],
  rf: number,
): number[] {
  const n = mu.length;
  const excess = mu.map((m) => m - rf);
  if (Math.max(...excess) <= 0) {
    throw new OptimizerInfeasibleError(
      "no asset has positive excess return over the risk-free rate; long-only tangency is undefined",
      { maxExcess: Math.max(...excess) },
    );
  }
  let active = excess
    .map((e, i) => (e > 0 ? i : -1))
    .filter((i) => i >= 0);

  for (let iter = 0; iter < n + 1; iter += 1) {
    if (active.length === 0) {
      throw new OptimizerInfeasibleError("long-only tangency active set became empty", {});
    }
    const subMu = subVector(mu, active);
    const subCov = subMatrix(cov, active);
    const subW = tangencyUnconstrained(subMu, subCov, rf);

    const minIdx = subW.reduce((iMin, v, i) => (v < (subW[iMin] as number) ? i : iMin), 0);
    const minVal = subW[minIdx] as number;
    if (minVal >= -1e-12) {
      const full = new Array<number>(n).fill(0);
      for (let k = 0; k < active.length; k += 1) {
        full[active[k] as number] = Math.max(subW[k] as number, 0);
      }
      const s = sumVec(full);
      if (s <= SUM_TOL) {
        throw new OptimizerInfeasibleError("long-only tangency produced zero weights", {
          sum: s,
        });
      }
      return full.map((v) => v / s);
    }
    active = active.filter((_, k) => k !== minIdx);
  }
  throw new OptimizerInfeasibleError(
    "long-only tangency failed to converge within n iterations",
    { n },
  );
}

export interface OptimizeMarkowitzInput {
  tickers: readonly string[];
  expectedReturns: readonly number[];
  covariance: number[][];
  riskFreeRate: number;
  allowShort: boolean;
  allowLeverage: boolean;
  warnings?: string[];
}

export function optimizeMarkowitz(input: OptimizeMarkowitzInput): ORP {
  const { tickers, expectedReturns, covariance, riskFreeRate, allowShort, warnings } = input;
  void input.allowLeverage;

  if (expectedReturns.length !== tickers.length) {
    throw new Error(
      `tickers length ${tickers.length} != expectedReturns length ${expectedReturns.length}`,
    );
  }
  if (covariance.length !== tickers.length) {
    throw new Error(`covariance must be ${tickers.length}x${tickers.length}`);
  }
  for (const v of expectedReturns) {
    if (!Number.isFinite(v)) {
      throw new OptimizerInfeasibleError("expectedReturns contain NaN or Inf", {
        tickers: [...tickers],
      });
    }
  }
  const cov = ensurePsdCovariance(covariance, warnings);

  let w = allowShort
    ? tangencyUnconstrained(expectedReturns, cov, riskFreeRate)
    : tangencyLongOnly(expectedReturns, cov, riskFreeRate);

  const s = sumVec(w);
  if (Math.abs(s - 1) > SUM_TOL) w = w.map((x) => x / s);

  const expectedReturn = dot(expectedReturns, w);
  const variance = dot(w, matVec(cov, w));
  if (variance <= 0) {
    throw new OptimizerInfeasibleError("ORP variance came out non-positive", {
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
