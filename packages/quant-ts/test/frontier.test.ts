import { describe, expect, it } from "vitest";

import {
  OptimizerInfeasibleError,
  calPoints,
  efficientFrontierPoints,
  dot,
  solve,
} from "../src/index.js";
import type { ORP } from "../src/index.js";
import { TOLERANCE_SCALAR, datasetA } from "../src/fixtures/datasetA.js";

describe("efficientFrontierPoints", () => {
  const cov = datasetA.covariance.matrix.map((r) => [...r]);
  const mu = [...datasetA.expectedReturns];

  it("returns exactly the requested resolution", () => {
    const pts = efficientFrontierPoints({
      expectedReturns: mu,
      covariance: cov,
      frontierResolution: 40,
    });
    expect(pts).toHaveLength(40);
  });

  it("is monotone in both axes", () => {
    const pts = efficientFrontierPoints({
      expectedReturns: mu,
      covariance: cov,
      frontierResolution: 40,
    });
    for (let i = 1; i < pts.length; i += 1) {
      expect((pts[i]!.expectedReturn) - (pts[i - 1]!.expectedReturn)).toBeGreaterThan(
        -TOLERANCE_SCALAR,
      );
      expect((pts[i]!.stdDev) - (pts[i - 1]!.stdDev)).toBeGreaterThan(-TOLERANCE_SCALAR);
    }
  });

  it("reproduces σ_MVP and σ_ORP via the Merton hyperbola", () => {
    const ones = [1, 1, 1];
    const invOnes = solve(cov, ones);
    const invMu = solve(cov, mu);
    const A = dot(ones, invOnes);
    const B = dot(ones, invMu);
    const C = dot(mu, invMu);
    const D = A * C - B * B;

    const sigmaAt = (mt: number): number =>
      Math.sqrt((A * mt * mt - 2 * B * mt + C) / D);

    expect(Math.abs(sigmaAt(datasetA.mvpExpectedReturn) - datasetA.mvpStdDev)).toBeLessThan(
      TOLERANCE_SCALAR,
    );
    expect(Math.abs(sigmaAt(datasetA.orpExpectedReturn) - datasetA.orpStdDev)).toBeLessThan(
      TOLERANCE_SCALAR,
    );
  });

  it("throws on resolution < 5", () => {
    expect(() =>
      efficientFrontierPoints({ expectedReturns: mu, covariance: cov, frontierResolution: 4 }),
    ).toThrow();
  });

  it("throws when discriminant is degenerate (constant μ)", () => {
    expect(() =>
      efficientFrontierPoints({
        expectedReturns: [0.1, 0.1, 0.1],
        covariance: [
          [0.04, 0, 0],
          [0, 0.09, 0],
          [0, 0, 0.16],
        ],
        frontierResolution: 20,
      }),
    ).toThrow(OptimizerInfeasibleError);
  });
});

describe("calPoints", () => {
  const orp: ORP = {
    weights: { ...datasetA.orpWeights },
    expectedReturn: datasetA.orpExpectedReturn,
    stdDev: datasetA.orpStdDev,
    variance: datasetA.orpVariance,
    sharpe: datasetA.orpSharpe,
  };

  it("passes through (0, rᶠ) and has Sharpe slope", () => {
    const pts = calPoints({ orp, riskFreeRate: datasetA.riskFreeRate, resolution: 21 });
    expect(pts[0]!.stdDev).toBe(0);
    expect(pts[0]!.expectedReturn).toBeCloseTo(datasetA.riskFreeRate, 12);
    for (let i = 1; i < pts.length; i += 1) {
      const slope = (pts[i]!.expectedReturn - datasetA.riskFreeRate) / Math.max(pts[i]!.stdDev, 1e-12);
      expect(slope).toBeCloseTo(datasetA.orpSharpe, 10);
    }
  });

  it("includes y_star in range", () => {
    const pts = calPoints({
      orp,
      riskFreeRate: datasetA.riskFreeRate,
      yStar: 1.5625,
      resolution: 21,
    });
    expect(Math.max(...pts.map((p) => p.y))).toBeGreaterThanOrEqual(1.5625);
  });

  it("throws on resolution < 2", () => {
    expect(() =>
      calPoints({ orp, riskFreeRate: datasetA.riskFreeRate, resolution: 1 }),
    ).toThrow();
  });

  it("throws on non-positive stdDev", () => {
    const degenerate: ORP = {
      weights: { X: 1 },
      expectedReturn: 0.1,
      stdDev: 0,
      variance: 0,
      sharpe: 0,
    };
    expect(() => calPoints({ orp: degenerate, riskFreeRate: 0.04 })).toThrow();
  });
});
