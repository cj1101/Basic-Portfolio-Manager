/**
 * TypeScript mirror of `backend/quant/returns.py`.
 *
 * Annualization factors follow `.cursor/rules/quant.mdc` §1:
 * - daily   × 252 (mean)  / × √252 (std)
 * - weekly  × 52          / × √52
 * - monthly × 12          / × √12
 */

import { InsufficientHistoryError, InvalidReturnWindowError } from "./errors.js";
import type { ReturnFrequency } from "./types.js";

export const ANNUALIZATION_FACTORS: Readonly<Record<ReturnFrequency, number>> = Object.freeze({
  daily: 252,
  weekly: 52,
  monthly: 12,
});

export function annualizationFactor(frequency: ReturnFrequency): number {
  return ANNUALIZATION_FACTORS[frequency];
}

export function annualizeMean(meanPerPeriod: number, frequency: ReturnFrequency): number {
  return meanPerPeriod * annualizationFactor(frequency);
}

export function annualizeStd(stdPerPeriod: number, frequency: ReturnFrequency): number {
  return stdPerPeriod * Math.sqrt(annualizationFactor(frequency));
}

export function annualizeVariance(variancePerPeriod: number, frequency: ReturnFrequency): number {
  return variancePerPeriod * annualizationFactor(frequency);
}

function require2D(returns: readonly (readonly number[])[]): {
  t: number;
  n: number;
} {
  const t = returns.length;
  if (t < 2) {
    throw new InsufficientHistoryError(
      "need at least 2 observations to compute statistics",
      { nObservations: t },
    );
  }
  const n = (returns[0] as readonly number[]).length;
  for (const row of returns) {
    if (row.length !== n) {
      throw new InvalidReturnWindowError("returns rows have inconsistent lengths");
    }
    for (const v of row) {
      if (!Number.isFinite(v)) {
        throw new InvalidReturnWindowError("returns contain NaN or Inf");
      }
    }
  }
  return { t, n };
}

export function expectedReturns(
  returns: readonly (readonly number[])[],
  frequency: ReturnFrequency,
): number[] {
  const { t, n } = require2D(returns);
  const factor = annualizationFactor(frequency);
  const out = new Array<number>(n).fill(0);
  for (let i = 0; i < t; i += 1) {
    const row = returns[i] as readonly number[];
    for (let j = 0; j < n; j += 1) out[j]! += row[j] as number;
  }
  return out.map((s) => (s / t) * factor);
}

export function stdDevs(
  returns: readonly (readonly number[])[],
  frequency: ReturnFrequency,
  ddof = 1,
): number[] {
  const { t, n } = require2D(returns);
  if (t - ddof <= 0) {
    throw new InsufficientHistoryError("degrees of freedom exhaust sample size", {
      nObservations: t,
      ddof,
    });
  }
  const factor = annualizationFactor(frequency);
  const sum = new Array<number>(n).fill(0);
  for (let i = 0; i < t; i += 1) {
    const row = returns[i] as readonly number[];
    for (let j = 0; j < n; j += 1) sum[j]! += row[j] as number;
  }
  const mean = sum.map((s) => s / t);
  const sq = new Array<number>(n).fill(0);
  for (let i = 0; i < t; i += 1) {
    const row = returns[i] as readonly number[];
    for (let j = 0; j < n; j += 1) {
      const diff = (row[j] as number) - (mean[j] as number);
      sq[j]! += diff * diff;
    }
  }
  return sq.map((s) => Math.sqrt(s / (t - ddof)) * Math.sqrt(factor));
}

export function sampleCovariance(
  returns: readonly (readonly number[])[],
  frequency: ReturnFrequency,
  ddof = 1,
): number[][] {
  const { t, n } = require2D(returns);
  if (t - ddof <= 0) {
    throw new InsufficientHistoryError("degrees of freedom exhaust sample size", {
      nObservations: t,
      ddof,
    });
  }
  const factor = annualizationFactor(frequency);
  const sum = new Array<number>(n).fill(0);
  for (let i = 0; i < t; i += 1) {
    const row = returns[i] as readonly number[];
    for (let j = 0; j < n; j += 1) sum[j]! += row[j] as number;
  }
  const mean = sum.map((s) => s / t);
  const cov: number[][] = Array.from({ length: n }, () => new Array<number>(n).fill(0));
  for (let k = 0; k < t; k += 1) {
    const row = returns[k] as readonly number[];
    for (let i = 0; i < n; i += 1) {
      const di = (row[i] as number) - (mean[i] as number);
      for (let j = i; j < n; j += 1) {
        const dj = (row[j] as number) - (mean[j] as number);
        (cov[i] as number[])[j] = ((cov[i] as number[])[j] as number) + di * dj;
      }
    }
  }
  for (let i = 0; i < n; i += 1) {
    for (let j = i; j < n; j += 1) {
      const v = (((cov[i] as number[])[j] as number) / (t - ddof)) * factor;
      (cov[i] as number[])[j] = v;
      (cov[j] as number[])[i] = v;
    }
  }
  return cov;
}
