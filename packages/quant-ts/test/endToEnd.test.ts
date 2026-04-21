import { describe, expect, it } from "vitest";

import {
  buildCovariance,
  calPoints,
  efficientFrontierPoints,
  minimumVariancePortfolio,
  optimizeMarkowitz,
  utilityMaxAllocation,
} from "../src/index.js";
import {
  TOLERANCE_SCALAR,
  TOLERANCE_WEIGHT_SUM,
  datasetA,
} from "../src/fixtures/datasetA.js";

describe("Dataset A end-to-end", () => {
  it("full pipeline matches every FIXTURES.md §1 number within 1e-6", () => {
    const warnings: string[] = [];

    const cov = buildCovariance(
      [...datasetA.stdDevs],
      datasetA.correlation.map((r) => [...r]),
    );
    for (let i = 0; i < 3; i += 1) {
      for (let j = 0; j < 3; j += 1) {
        expect(Math.abs((cov[i]![j] as number) - (datasetA.covariance.matrix[i]![j] as number)))
          .toBeLessThan(1e-12);
      }
    }

    const orp = optimizeMarkowitz({
      tickers: [...datasetA.tickers],
      expectedReturns: [...datasetA.expectedReturns],
      covariance: cov,
      riskFreeRate: datasetA.riskFreeRate,
      allowShort: true,
      allowLeverage: true,
      warnings,
    });
    for (const [t, v] of Object.entries(datasetA.orpWeights)) {
      expect(Math.abs(orp.weights[t]! - v)).toBeLessThan(TOLERANCE_SCALAR);
    }
    expect(Math.abs(orp.expectedReturn - datasetA.orpExpectedReturn)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(orp.stdDev - datasetA.orpStdDev)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(orp.variance - datasetA.orpVariance)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(orp.sharpe - datasetA.orpSharpe)).toBeLessThan(TOLERANCE_SCALAR);
    const orpSum = Object.values(orp.weights).reduce((a, b) => a + b, 0);
    expect(Math.abs(orpSum - 1)).toBeLessThan(TOLERANCE_WEIGHT_SUM);

    const mvp = minimumVariancePortfolio({
      tickers: [...datasetA.tickers],
      expectedReturns: [...datasetA.expectedReturns],
      covariance: cov,
      riskFreeRate: datasetA.riskFreeRate,
      allowShort: true,
      warnings,
    });
    for (const [t, v] of Object.entries(datasetA.mvpWeights)) {
      expect(Math.abs(mvp.weights[t]! - v)).toBeLessThan(TOLERANCE_SCALAR);
    }
    expect(Math.abs(mvp.expectedReturn - datasetA.mvpExpectedReturn)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(mvp.stdDev - datasetA.mvpStdDev)).toBeLessThan(TOLERANCE_SCALAR);

    const complete4 = utilityMaxAllocation({
      orp,
      riskFreeRate: datasetA.riskFreeRate,
      riskProfile: { riskAversion: 4 },
      allowLeverage: true,
      warnings,
    });
    expect(Math.abs(complete4.yStar - 1.5625)).toBeLessThan(TOLERANCE_SCALAR);
    expect(complete4.leverageUsed).toBe(true);
    expect(Math.abs(complete4.expectedReturn - 0.170625)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(complete4.stdDev - 0.180711)).toBeLessThan(TOLERANCE_SCALAR);

    const complete8 = utilityMaxAllocation({
      orp,
      riskFreeRate: datasetA.riskFreeRate,
      riskProfile: { riskAversion: 8 },
      allowLeverage: true,
      warnings,
    });
    expect(Math.abs(complete8.yStar - 0.78125)).toBeLessThan(TOLERANCE_SCALAR);
    expect(complete8.leverageUsed).toBe(false);
    expect(Math.abs(complete8.expectedReturn - 0.105313)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(complete8.stdDev - 0.090356)).toBeLessThan(TOLERANCE_SCALAR);

    const frontier = efficientFrontierPoints({
      expectedReturns: [...datasetA.expectedReturns],
      covariance: cov,
      frontierResolution: 40,
      warnings,
    });
    expect(frontier).toHaveLength(40);

    const cal = calPoints({
      orp,
      riskFreeRate: datasetA.riskFreeRate,
      yStar: complete4.yStar,
      resolution: 21,
    });
    expect(cal[0]!.stdDev).toBe(0);
    expect(cal[0]!.expectedReturn).toBeCloseTo(datasetA.riskFreeRate, 12);
    expect(Math.max(...cal.map((p) => p.y))).toBeGreaterThanOrEqual(1.5625);

    expect(warnings).toHaveLength(0);
  });
});
