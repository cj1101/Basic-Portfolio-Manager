import { describe, expect, it } from "vitest";
import { optimizationResultSample } from "../src/fixtures/optimizationResultSample";
import type { OptimizationResult } from "../src/types/contracts";
import { computeCompleteFromORP } from "../src/lib/completePortfolio";
import { calFromORP } from "../src/lib/calFromORP";
import { scoreQuestionnaire, questionnaire } from "../src/fixtures/questionnaire";

describe("optimizationResultSample", () => {
  it("matches the OptimizationResult contract at compile time", () => {
    // If this import type-checks and the assignment below type-checks, we're fine.
    const typed: OptimizationResult = optimizationResultSample;
    expect(typed.requestId).toBe("opt_sample_phase0");
  });

  it("ORP weights sum to 1 within 1e-9", () => {
    const sum = Object.values(optimizationResultSample.orp.weights).reduce((a, b) => a + b, 0);
    expect(Math.abs(sum - 1)).toBeLessThan(1e-9);
  });

  it("covariance matrix is symmetric and matches the ticker list", () => {
    const { tickers, matrix } = optimizationResultSample.covariance;
    expect(matrix.length).toBe(tickers.length);
    for (let i = 0; i < matrix.length; i += 1) {
      const row = matrix[i];
      expect(row).toBeDefined();
      expect(row!.length).toBe(tickers.length);
      for (let j = 0; j < matrix.length; j += 1) {
        const a = matrix[i]![j];
        const b = matrix[j]![i];
        expect(a).toBeDefined();
        expect(b).toBeDefined();
        expect(Math.abs((a as number) - (b as number))).toBeLessThan(1e-12);
      }
    }
  });

  it("frontier points are monotone non-decreasing in stdDev", () => {
    const pts = optimizationResultSample.frontierPoints;
    for (let i = 1; i < pts.length; i += 1) {
      expect(pts[i]!.stdDev).toBeGreaterThanOrEqual(pts[i - 1]!.stdDev);
    }
  });
});

describe("computeCompleteFromORP", () => {
  const { orp, riskFreeRate } = optimizationResultSample;

  it("reproduces y* = (E(r) - r_f) / (A * variance)", () => {
    const out = computeCompleteFromORP(orp, riskFreeRate, { riskAversion: 3 });
    const expected = (orp.expectedReturn - riskFreeRate) / (3 * orp.variance);
    expect(out.yStar).toBeCloseTo(expected, 12);
  });

  it("weights sum to 1 including risk-free", () => {
    const out = computeCompleteFromORP(orp, riskFreeRate, { riskAversion: 4 });
    const sum =
      out.weightRiskFree + Object.values(out.weights).reduce((a, b) => a + b, 0);
    expect(sum).toBeCloseTo(1, 12);
  });

  it("engages leverage override when target return is aggressive enough to exceed y*", () => {
    // With A = 8 the utility-max y* is ~0.48. A target of 0.35 > E(r_ORP) forces y > 1.
    const out = computeCompleteFromORP(orp, riskFreeRate, {
      riskAversion: 8,
      targetReturn: 0.35,
    });
    expect(out.leverageUsed).toBe(true);
    expect(out.targetReturnOverride).toBe(true);
    expect(out.yStar).toBeGreaterThan(1);
  });

  it("does not override y* when utility-max y* already exceeds yTarget", () => {
    // A = 3 gives y* ≈ 1.28 > yTarget ≈ 1.21 for targetReturn = E(r_ORP) + 0.05.
    // The target-return rule says max(y*, yTarget), so y* wins.
    const out = computeCompleteFromORP(orp, riskFreeRate, {
      riskAversion: 3,
      targetReturn: orp.expectedReturn + 0.05,
    });
    expect(out.targetReturnOverride).toBe(false);
  });

  it("does not override y* when target return is below ORP expected return", () => {
    const baseline = computeCompleteFromORP(orp, riskFreeRate, { riskAversion: 3 });
    const withLowTarget = computeCompleteFromORP(orp, riskFreeRate, {
      riskAversion: 3,
      targetReturn: 0.1,
    });
    expect(withLowTarget.yStar).toBeCloseTo(baseline.yStar, 12);
    expect(withLowTarget.targetReturnOverride).toBe(false);
  });
});

describe("calFromORP", () => {
  it("starts at (0, r_f) and passes through (σ_ORP, E(r_ORP))", () => {
    const { orp, riskFreeRate } = optimizationResultSample;
    const points = calFromORP(orp, riskFreeRate, { yMax: 1, steps: 10 });
    expect(points[0]!.stdDev).toBe(0);
    expect(points[0]!.expectedReturn).toBeCloseTo(riskFreeRate, 12);
    const last = points[points.length - 1]!;
    expect(last.stdDev).toBeCloseTo(orp.stdDev, 12);
    expect(last.expectedReturn).toBeCloseTo(orp.expectedReturn, 12);
  });
});

describe("questionnaire scoring", () => {
  it("returns a value in [1, 10] for a full answer set", () => {
    const allAnswers: Record<string, string> = {};
    for (const q of questionnaire) {
      allAnswers[q.id] = q.options[0]!.id;
    }
    const A = scoreQuestionnaire(allAnswers);
    expect(A).toBeGreaterThanOrEqual(1);
    expect(A).toBeLessThanOrEqual(10);
  });
});
