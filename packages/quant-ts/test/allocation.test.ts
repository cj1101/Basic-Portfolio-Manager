import { describe, expect, it } from "vitest";

import { InvalidRiskProfileError, utilityMaxAllocation } from "../src/index.js";
import type { ORP } from "../src/index.js";
import {
  TOLERANCE_SCALAR,
  TOLERANCE_WEIGHT_SUM,
  datasetA,
} from "../src/fixtures/datasetA.js";

function orpFromDatasetA(): ORP {
  return {
    weights: { ...datasetA.orpWeights },
    expectedReturn: datasetA.orpExpectedReturn,
    stdDev: datasetA.orpStdDev,
    variance: datasetA.orpVariance,
    sharpe: datasetA.orpSharpe,
  };
}

describe("utilityMaxAllocation — Dataset A A=4 (leverage)", () => {
  const complete = utilityMaxAllocation({
    orp: orpFromDatasetA(),
    riskFreeRate: datasetA.riskFreeRate,
    riskProfile: { riskAversion: 4 },
    allowLeverage: true,
  });

  it("y_star = 1.5625, leverage used", () => {
    expect(complete.yStar).toBeCloseTo(1.5625, 10);
    expect(complete.leverageUsed).toBe(true);
    expect(complete.weightRiskFree).toBeCloseTo(-0.5625, 10);
  });

  it("risky weights", () => {
    expect(complete.weights.S1!).toBeCloseTo(2 / 3, 6);
    expect(complete.weights.S2!).toBeCloseTo(9 / 16, 6);
    expect(complete.weights.S3!).toBeCloseTo(1 / 3, 6);
    const total = Object.values(complete.weights).reduce((a, b) => a + b, 0) + complete.weightRiskFree;
    expect(Math.abs(total - 1)).toBeLessThan(TOLERANCE_WEIGHT_SUM);
  });

  it("moments", () => {
    expect(Math.abs(complete.expectedReturn - 0.170625)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(complete.stdDev - 0.180711)).toBeLessThan(TOLERANCE_SCALAR);
  });
});

describe("utilityMaxAllocation — Dataset A A=8 (no leverage)", () => {
  const complete = utilityMaxAllocation({
    orp: orpFromDatasetA(),
    riskFreeRate: datasetA.riskFreeRate,
    riskProfile: { riskAversion: 8 },
    allowLeverage: true,
  });

  it("y_star = 0.78125, leverage not used", () => {
    expect(complete.yStar).toBeCloseTo(0.78125, 10);
    expect(complete.leverageUsed).toBe(false);
    expect(complete.weightRiskFree).toBeCloseTo(0.21875, 10);
  });

  it("risky weights", () => {
    expect(complete.weights.S1!).toBeCloseTo(1 / 3, 6);
    expect(complete.weights.S2!).toBeCloseTo(9 / 32, 6);
    expect(complete.weights.S3!).toBeCloseTo(1 / 6, 6);
  });

  it("moments", () => {
    expect(Math.abs(complete.expectedReturn - 0.105313)).toBeLessThan(TOLERANCE_SCALAR);
    expect(Math.abs(complete.stdDev - 0.090356)).toBeLessThan(TOLERANCE_SCALAR);
  });
});

describe("utilityMaxAllocation — target return override", () => {
  it("target below ORP does not override", () => {
    const warnings: string[] = [];
    const complete = utilityMaxAllocation({
      orp: orpFromDatasetA(),
      riskFreeRate: datasetA.riskFreeRate,
      riskProfile: { riskAversion: 8, targetReturn: 0.08 },
      allowLeverage: true,
      warnings,
    });
    expect(complete.yStar).toBeCloseTo(0.78125, 10);
    expect(warnings).toHaveLength(0);
  });

  it("target above ORP overrides with warning", () => {
    const warnings: string[] = [];
    const complete = utilityMaxAllocation({
      orp: orpFromDatasetA(),
      riskFreeRate: datasetA.riskFreeRate,
      riskProfile: { riskAversion: 8, targetReturn: 0.2 },
      allowLeverage: true,
      warnings,
    });
    const expectedY = (0.2 - datasetA.riskFreeRate) / (datasetA.orpExpectedReturn - datasetA.riskFreeRate);
    expect(complete.yStar).toBeCloseTo(expectedY, 6);
    expect(complete.leverageUsed).toBe(true);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain("targetReturn");
  });
});

describe("utilityMaxAllocation — leverage clamp", () => {
  it("disallowed leverage clamps y to 1", () => {
    const warnings: string[] = [];
    const complete = utilityMaxAllocation({
      orp: orpFromDatasetA(),
      riskFreeRate: datasetA.riskFreeRate,
      riskProfile: { riskAversion: 4 },
      allowLeverage: false,
      warnings,
    });
    expect(complete.yStar).toBeCloseTo(1, 10);
    expect(complete.leverageUsed).toBe(false);
    expect(complete.weightRiskFree).toBeCloseTo(0, 10);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain("leverage disabled");
  });
});

describe("utilityMaxAllocation — invalid profiles", () => {
  it("negative risk premium raises", () => {
    const orp: ORP = {
      weights: { ...datasetA.orpWeights },
      expectedReturn: 0.02,
      stdDev: datasetA.orpStdDev,
      variance: datasetA.orpVariance,
      sharpe: -1,
    };
    expect(() =>
      utilityMaxAllocation({
        orp,
        riskFreeRate: datasetA.riskFreeRate,
        riskProfile: { riskAversion: 4 },
        allowLeverage: true,
      }),
    ).toThrow(InvalidRiskProfileError);
  });

  it("zero variance raises", () => {
    const orp: ORP = {
      weights: { ...datasetA.orpWeights },
      expectedReturn: 0.1,
      stdDev: 0,
      variance: 0,
      sharpe: 0,
    };
    expect(() =>
      utilityMaxAllocation({
        orp,
        riskFreeRate: datasetA.riskFreeRate,
        riskProfile: { riskAversion: 4 },
        allowLeverage: true,
      }),
    ).toThrow(InvalidRiskProfileError);
  });

  it("target return with zero risk premium raises", () => {
    const orp: ORP = {
      weights: { ...datasetA.orpWeights },
      expectedReturn: datasetA.riskFreeRate,
      stdDev: datasetA.orpStdDev,
      variance: datasetA.orpVariance,
      sharpe: 0,
    };
    expect(() =>
      utilityMaxAllocation({
        orp,
        riskFreeRate: datasetA.riskFreeRate,
        riskProfile: { riskAversion: 4, targetReturn: 0.1 },
        allowLeverage: true,
      }),
    ).toThrow(InvalidRiskProfileError);
  });
});
