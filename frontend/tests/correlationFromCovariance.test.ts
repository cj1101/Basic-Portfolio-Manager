import { describe, expect, it } from "vitest";
import { optimizationResultSample } from "../src/fixtures/optimizationResultSample";
import {
  correlationFromCovariance,
  ensureOptimizationResultHasCorrelation,
} from "../src/lib/correlationFromCovariance";
import type { OptimizationResult } from "../src/types/contracts";

describe("correlationFromCovariance", () => {
  it("round-trips the fixture covariance", () => {
    const r = correlationFromCovariance(optimizationResultSample.covariance);
    expect(r.tickers).toEqual(optimizationResultSample.covariance.tickers);
    expect(r.matrix[0]![0]).toBe(1);
    const expected = optimizationResultSample.correlation.matrix[0]![1]!;
    expect(r.matrix[0]![1]).toBeCloseTo(expected, 4);
  });

  it("fills missing correlation on a legacy result shape", () => {
    const { correlation: _c, ...rest } = optimizationResultSample;
    const legacy = rest as unknown as OptimizationResult;
    const fixed = ensureOptimizationResultHasCorrelation(legacy);
    expect(fixed.correlation.matrix[0]![0]).toBe(1);
    expect(fixed.correlation.matrix[0]![1]).toBeCloseTo(optimizationResultSample.correlation.matrix[0]![1]!, 4);
  });
});
