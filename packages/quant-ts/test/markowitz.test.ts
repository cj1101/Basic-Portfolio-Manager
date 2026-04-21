import { describe, expect, it } from "vitest";

import {
  OptimizerInfeasibleError,
  OptimizerNonPsdCovarianceError,
  optimizeMarkowitz,
} from "../src/index.js";
import {
  TOLERANCE_SCALAR,
  TOLERANCE_WEIGHT_SUM,
  datasetA,
} from "../src/fixtures/datasetA.js";

describe("optimizeMarkowitz — Dataset A unconstrained", () => {
  const orp = optimizeMarkowitz({
    tickers: [...datasetA.tickers],
    expectedReturns: [...datasetA.expectedReturns],
    covariance: datasetA.covariance.matrix.map((row) => [...row]),
    riskFreeRate: datasetA.riskFreeRate,
    allowShort: true,
    allowLeverage: true,
  });

  it("matches ORP weights", () => {
    for (const [ticker, expected] of Object.entries(datasetA.orpWeights)) {
      expect(Math.abs(orp.weights[ticker]! - expected)).toBeLessThan(TOLERANCE_SCALAR);
    }
  });

  it("weights sum to 1", () => {
    const total = Object.values(orp.weights).reduce((a, b) => a + b, 0);
    expect(Math.abs(total - 1)).toBeLessThan(TOLERANCE_WEIGHT_SUM);
  });

  it("matches ORP moments and Sharpe", () => {
    expect(Math.abs(orp.expectedReturn - datasetA.orpExpectedReturn)).toBeLessThan(
      TOLERANCE_SCALAR,
    );
    expect(Math.abs(orp.stdDev - datasetA.orpStdDev)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(orp.variance - datasetA.orpVariance)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(orp.sharpe - datasetA.orpSharpe)).toBeLessThan(TOLERANCE_SCALAR);
  });
});

describe("optimizeMarkowitz — Dataset A long-only", () => {
  it("matches unconstrained when all excess returns are positive", () => {
    const orp = optimizeMarkowitz({
      tickers: [...datasetA.tickers],
      expectedReturns: [...datasetA.expectedReturns],
      covariance: datasetA.covariance.matrix.map((row) => [...row]),
      riskFreeRate: datasetA.riskFreeRate,
      allowShort: false,
      allowLeverage: true,
    });
    for (const [ticker, expected] of Object.entries(datasetA.orpWeights)) {
      expect(Math.abs(orp.weights[ticker]! - expected)).toBeLessThan(1e-4);
    }
    for (const w of Object.values(orp.weights)) expect(w).toBeGreaterThanOrEqual(-1e-9);
  });

  it("rejects long-only when no positive excess", () => {
    expect(() =>
      optimizeMarkowitz({
        tickers: ["A", "B"],
        expectedReturns: [0.01, 0.02],
        covariance: [
          [0.04, 0],
          [0, 0.09],
        ],
        riskFreeRate: 0.05,
        allowShort: false,
        allowLeverage: true,
      }),
    ).toThrow(OptimizerInfeasibleError);
  });
});

describe("optimizeMarkowitz — shape / validation", () => {
  const baseCov = datasetA.covariance.matrix.map((row) => [...row]);

  it("rejects ticker length mismatch", () => {
    expect(() =>
      optimizeMarkowitz({
        tickers: ["S1", "S2"],
        expectedReturns: [...datasetA.expectedReturns],
        covariance: baseCov,
        riskFreeRate: datasetA.riskFreeRate,
        allowShort: true,
        allowLeverage: true,
      }),
    ).toThrow();
  });

  it("rejects covariance shape mismatch", () => {
    expect(() =>
      optimizeMarkowitz({
        tickers: [...datasetA.tickers],
        expectedReturns: [...datasetA.expectedReturns],
        covariance: [
          [1, 0],
          [0, 1],
        ],
        riskFreeRate: datasetA.riskFreeRate,
        allowShort: true,
        allowLeverage: true,
      }),
    ).toThrow();
  });

  it("rejects non-finite μ", () => {
    expect(() =>
      optimizeMarkowitz({
        tickers: [...datasetA.tickers],
        expectedReturns: [NaN, 0.13, 0.16],
        covariance: baseCov,
        riskFreeRate: datasetA.riskFreeRate,
        allowShort: true,
        allowLeverage: true,
      }),
    ).toThrow(OptimizerInfeasibleError);
  });

  it("rejects non-PSD covariance", () => {
    expect(() =>
      optimizeMarkowitz({
        tickers: [...datasetA.tickers],
        expectedReturns: [...datasetA.expectedReturns],
        covariance: [
          [1, 2, 0],
          [2, 1, 0],
          [0, 0, 1],
        ],
        riskFreeRate: datasetA.riskFreeRate,
        allowShort: true,
        allowLeverage: true,
      }),
    ).toThrow(OptimizerNonPsdCovarianceError);
  });
});
