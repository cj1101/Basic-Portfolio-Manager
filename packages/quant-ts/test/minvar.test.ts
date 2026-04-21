import { describe, expect, it } from "vitest";

import { minimumVariancePortfolio } from "../src/index.js";
import {
  TOLERANCE_SCALAR,
  TOLERANCE_WEIGHT_SUM,
  datasetA,
} from "../src/fixtures/datasetA.js";

describe("minimumVariancePortfolio — Dataset A unconstrained", () => {
  const mvp = minimumVariancePortfolio({
    tickers: [...datasetA.tickers],
    expectedReturns: [...datasetA.expectedReturns],
    covariance: datasetA.covariance.matrix.map((r) => [...r]),
    riskFreeRate: datasetA.riskFreeRate,
    allowShort: true,
  });

  it("weights", () => {
    for (const [t, v] of Object.entries(datasetA.mvpWeights)) {
      expect(Math.abs(mvp.weights[t]! - v)).toBeLessThan(TOLERANCE_SCALAR);
    }
    const total = Object.values(mvp.weights).reduce((a, b) => a + b, 0);
    expect(Math.abs(total - 1)).toBeLessThan(TOLERANCE_WEIGHT_SUM);
  });

  it("moments", () => {
    expect(Math.abs(mvp.expectedReturn - datasetA.mvpExpectedReturn)).toBeLessThan(
      TOLERANCE_SCALAR,
    );
    expect(Math.abs(mvp.stdDev - datasetA.mvpStdDev)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(mvp.variance - datasetA.mvpVariance)).toBeLessThan(TOLERANCE_SCALAR);
  });
});

describe("minimumVariancePortfolio — long-only", () => {
  it("matches closed-form diagonal case", () => {
    const mvp = minimumVariancePortfolio({
      tickers: ["X", "Y"],
      expectedReturns: [0.05, 0.1],
      covariance: [
        [0.04, 0],
        [0, 0.09],
      ],
      riskFreeRate: 0.04,
      allowShort: false,
    });
    expect(mvp.weights.X!).toBeCloseTo(9 / 13, 10);
    expect(mvp.weights.Y!).toBeCloseTo(4 / 13, 10);
  });

  it("matches unconstrained when all weights are already non-negative", () => {
    const mvp = minimumVariancePortfolio({
      tickers: [...datasetA.tickers],
      expectedReturns: [...datasetA.expectedReturns],
      covariance: datasetA.covariance.matrix.map((r) => [...r]),
      riskFreeRate: datasetA.riskFreeRate,
      allowShort: false,
    });
    for (const [t, v] of Object.entries(datasetA.mvpWeights)) {
      expect(Math.abs(mvp.weights[t]! - v)).toBeLessThan(1e-4);
    }
  });
});

describe("minimumVariancePortfolio — validation", () => {
  it("rejects length mismatch", () => {
    expect(() =>
      minimumVariancePortfolio({
        tickers: ["S1"],
        expectedReturns: [...datasetA.expectedReturns],
        covariance: datasetA.covariance.matrix.map((r) => [...r]),
        riskFreeRate: 0.04,
        allowShort: true,
      }),
    ).toThrow();
  });

  it("rejects covariance shape mismatch", () => {
    expect(() =>
      minimumVariancePortfolio({
        tickers: [...datasetA.tickers],
        expectedReturns: [...datasetA.expectedReturns],
        covariance: [
          [1, 0],
          [0, 1],
        ],
        riskFreeRate: 0.04,
        allowShort: true,
      }),
    ).toThrow();
  });
});
