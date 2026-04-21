/**
 * Efficient frontier (Merton closed form) and Capital Allocation Line —
 * TypeScript mirror of `backend/quant/frontier.py`.
 */

import { OptimizerInfeasibleError } from "./errors.js";
import { dot, ensurePsdCovariance, solve } from "./linalg.js";
import type { CALPoint, FrontierPoint, ORP } from "./types.js";

export const DISCRIMINANT_TOL = 1e-12;

export interface EfficientFrontierInput {
  expectedReturns: readonly number[];
  covariance: number[][];
  frontierResolution?: number;
  upperReturnExtension?: number;
  warnings?: string[];
}

export function efficientFrontierPoints(input: EfficientFrontierInput): FrontierPoint[] {
  const {
    expectedReturns: mu,
    covariance,
    frontierResolution = 40,
    upperReturnExtension = 1.5,
    warnings,
  } = input;

  if (frontierResolution < 5) {
    throw new Error(`frontierResolution must be ≥ 5; got ${frontierResolution}`);
  }
  const cov = ensurePsdCovariance(covariance, warnings);

  const n = mu.length;
  const ones = new Array<number>(n).fill(1);
  const invOnes = solve(cov, ones);
  const invMu = solve(cov, Array.from(mu));

  const A = dot(ones, invOnes);
  const B = dot(ones, invMu);
  const C = dot(Array.from(mu), invMu);
  const D = A * C - B * B;

  if (D <= DISCRIMINANT_TOL || A <= 0) {
    throw new OptimizerInfeasibleError(
      "frontier discriminant is non-positive; inputs are degenerate",
      { A, B, C, D },
    );
  }

  const muMvp = B / A;
  const muTop = Math.max(...mu);
  const span = Math.max(muTop - muMvp, 1e-9);
  const muUpper = muTop + upperReturnExtension * span;

  const points: FrontierPoint[] = [];
  for (let i = 0; i < frontierResolution; i += 1) {
    const t = i / (frontierResolution - 1);
    const muTarget = muMvp + (muUpper - muMvp) * t;
    const variance = (A * muTarget * muTarget - 2 * B * muTarget + C) / D;
    if (variance < 0) continue;
    points.push({ stdDev: Math.sqrt(variance), expectedReturn: muTarget });
  }
  return points;
}

export interface CALPointsInput {
  orp: ORP;
  riskFreeRate: number;
  yStar?: number;
  resolution?: number;
  margin?: number;
}

export function calPoints(input: CALPointsInput): CALPoint[] {
  const { orp, riskFreeRate, yStar, resolution = 21, margin = 0.5 } = input;
  if (resolution < 2) throw new Error(`resolution must be ≥ 2; got ${resolution}`);
  if (orp.stdDev <= 0) throw new Error(`orp.stdDev must be > 0; got ${orp.stdDev}`);

  const excess = orp.expectedReturn - riskFreeRate;
  const yTop = yStar === undefined ? 1 : Math.max(1, yStar);
  const yMax = yTop + margin;

  const points: CALPoint[] = [];
  for (let i = 0; i < resolution; i += 1) {
    const y = (i / (resolution - 1)) * yMax;
    points.push({
      stdDev: y * orp.stdDev,
      expectedReturn: riskFreeRate + y * excess,
      y,
    });
  }
  return points;
}
