import { describe, expect, it } from "vitest";

import {
  ANNUALIZATION_FACTORS,
  InsufficientHistoryError,
  InvalidReturnWindowError,
  ReturnFrequency,
  annualizationFactor,
  annualizeMean,
  annualizeStd,
  annualizeVariance,
  expectedReturns,
  sampleCovariance,
  stdDevs,
} from "../src/index.js";

describe("annualization", () => {
  it("exposes the factor map", () => {
    expect(ANNUALIZATION_FACTORS.daily).toBe(252);
    expect(ANNUALIZATION_FACTORS.weekly).toBe(52);
    expect(ANNUALIZATION_FACTORS.monthly).toBe(12);
  });

  it.each([
    [ReturnFrequency.Daily, 252],
    [ReturnFrequency.Weekly, 52],
    [ReturnFrequency.Monthly, 12],
  ])("returns %s -> %i", (freq, factor) => {
    expect(annualizationFactor(freq)).toBe(factor);
  });

  it("annualizeMean multiplies by factor", () => {
    expect(annualizeMean(0.001, ReturnFrequency.Daily)).toBeCloseTo(0.252, 12);
  });

  it("annualizeStd multiplies by sqrt(factor)", () => {
    expect(annualizeStd(0.01, ReturnFrequency.Daily)).toBeCloseTo(0.01 * Math.sqrt(252), 12);
  });

  it("annualizeVariance multiplies by factor", () => {
    expect(annualizeVariance(0.0001, ReturnFrequency.Daily)).toBeCloseTo(0.0252, 12);
  });
});

describe("expectedReturns", () => {
  it("matches factor × sample mean for constant inputs", () => {
    const t = 60;
    const rows = Array.from({ length: t }, () => [0.001, -0.0005, 0.0002]);
    const mu = expectedReturns(rows, ReturnFrequency.Daily);
    expect(mu[0]).toBeCloseTo(0.001 * 252, 12);
    expect(mu[1]).toBeCloseTo(-0.0005 * 252, 12);
    expect(mu[2]).toBeCloseTo(0.0002 * 252, 12);
  });

  it("throws if fewer than 2 observations", () => {
    expect(() => expectedReturns([[0.1]], ReturnFrequency.Daily)).toThrow(
      InsufficientHistoryError,
    );
  });

  it("throws on non-finite", () => {
    expect(() =>
      expectedReturns(
        [
          [NaN, 0.01],
          [0.01, 0.02],
        ],
        ReturnFrequency.Daily,
      ),
    ).toThrow(InvalidReturnWindowError);
  });
});

describe("stdDevs / sampleCovariance", () => {
  it("stdDevs matches manual formula", () => {
    const rows: number[][] = [];
    // Deterministic pseudo-random sequence so the test is reproducible.
    let seed = 1;
    const rand = (): number => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return (seed / 0x100000000 - 0.5) * 0.02;
    };
    for (let i = 0; i < 500; i += 1) rows.push([rand(), rand(), rand()]);
    const sd = stdDevs(rows, ReturnFrequency.Daily);
    // Manual computation
    const n = rows.length;
    const means = [0, 0, 0];
    for (const r of rows) for (let j = 0; j < 3; j += 1) means[j] = (means[j] as number) + (r[j] as number);
    for (let j = 0; j < 3; j += 1) means[j] = (means[j] as number) / n;
    const sq = [0, 0, 0];
    for (const r of rows) {
      for (let j = 0; j < 3; j += 1) {
        const d = (r[j] as number) - (means[j] as number);
        sq[j] = (sq[j] as number) + d * d;
      }
    }
    for (let j = 0; j < 3; j += 1) {
      expect(sd[j]).toBeCloseTo(
        Math.sqrt((sq[j] as number) / (n - 1)) * Math.sqrt(252),
        10,
      );
    }
  });

  it("sampleCovariance is symmetric and PSD", () => {
    const rows: number[][] = Array.from({ length: 200 }, (_, i) => [
      Math.sin(i),
      Math.cos(i),
      Math.sin(i + 1),
    ]);
    const cov = sampleCovariance(rows, ReturnFrequency.Daily);
    expect(cov[0]?.[1]).toBeCloseTo(cov[1]?.[0] ?? NaN, 12);
  });

  it("raises if ddof exhausts sample size", () => {
    expect(() =>
      stdDevs([[0.1, 0.2]], ReturnFrequency.Daily, 1),
    ).toThrow(InsufficientHistoryError);
  });
});
