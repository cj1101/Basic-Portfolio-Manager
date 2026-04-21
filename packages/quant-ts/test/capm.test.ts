import { describe, expect, it } from "vitest";

import {
  capmRequiredReturn,
  capmSystematicVariance,
  capmTotalExpectedReturn,
  capmTotalStdDev,
  capmTotalVariance,
} from "../src/index.js";
import { TOLERANCE_SCALAR, datasetACAPM } from "../src/fixtures/datasetA.js";

const d = datasetACAPM;

describe("CAPM — Dataset A single-stock", () => {
  it("requiredReturn", () => {
    expect(
      capmRequiredReturn(d.beta, d.marketExpectedReturn, d.riskFreeRate),
    ).toBeCloseTo(d.requiredReturn, 6);
  });

  it("totalExpectedReturn", () => {
    expect(
      capmTotalExpectedReturn(d.beta, d.alpha, d.marketExpectedReturn, d.riskFreeRate),
    ).toBeCloseTo(d.totalExpectedReturn, 6);
  });

  it("systematicVariance", () => {
    expect(capmSystematicVariance(d.beta, d.marketVariance)).toBeCloseTo(
      d.systematicVariance,
      6,
    );
  });

  it("totalVariance", () => {
    expect(
      capmTotalVariance(d.beta, d.marketVariance, d.firmSpecificVar),
    ).toBeCloseTo(d.totalVariance, 6);
  });

  it("totalStdDev", () => {
    expect(
      capmTotalStdDev(d.beta, d.marketVariance, d.firmSpecificVar),
    ).toBeCloseTo(d.stdDev, 6);
  });

  it("tolerance check", () => {
    expect(Math.abs(capmRequiredReturn(d.beta, d.marketExpectedReturn, d.riskFreeRate) - d.requiredReturn))
      .toBeLessThan(TOLERANCE_SCALAR);
  });
});

describe("CAPM — edge cases", () => {
  it("zero beta yields risk-free", () => {
    expect(capmRequiredReturn(0, 0.1, 0.04)).toBeCloseTo(0.04, 12);
  });

  it("beta=1 yields market", () => {
    expect(capmRequiredReturn(1, 0.1, 0.04)).toBeCloseTo(0.1, 12);
  });

  it("rejects negative market variance", () => {
    expect(() => capmSystematicVariance(1, -0.01)).toThrow();
  });

  it("rejects negative firm-specific variance", () => {
    expect(() => capmTotalVariance(1, 0.01, -0.01)).toThrow();
  });
});
