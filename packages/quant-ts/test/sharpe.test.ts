import { describe, expect, it } from "vitest";

import { sharpeRatio } from "../src/index.js";
import { TOLERANCE_SCALAR, datasetA } from "../src/fixtures/datasetA.js";

describe("sharpeRatio", () => {
  it("matches Dataset A ORP Sharpe", () => {
    const sr = sharpeRatio(
      datasetA.orpExpectedReturn,
      datasetA.orpStdDev,
      datasetA.riskFreeRate,
    );
    expect(sr).toBeCloseTo(datasetA.orpSharpe, 10);
    expect(sr).toBeCloseTo(Math.sqrt(0.5225), 6);
    expect(Math.abs(sr - datasetA.orpSharpe)).toBeLessThan(TOLERANCE_SCALAR);
  });

  it("throws when std_dev is zero", () => {
    expect(() => sharpeRatio(0.1, 0, 0.04)).toThrow();
  });

  it("throws on non-finite input", () => {
    expect(() => sharpeRatio(Number.NaN, 0.2, 0.04)).toThrow();
  });
});
