import { describe, expect, it } from "vitest";

import {
  InsufficientHistoryError,
  InvalidReturnWindowError,
  singleIndexMetrics,
} from "../src/index.js";

function seededNormal(seed: number): () => number {
  let s = seed;
  return () => {
    // Box-Muller with mulberry32 seed.
    s = (s + 0x6d2b79f5) >>> 0;
    let t1 = s;
    t1 = Math.imul(t1 ^ (t1 >>> 15), t1 | 1);
    t1 ^= t1 + Math.imul(t1 ^ (t1 >>> 7), t1 | 61);
    const u1 = ((t1 ^ (t1 >>> 14)) >>> 0) / 4294967296 || 1e-12;
    s = (s + 0x6d2b79f5) >>> 0;
    let t2 = s;
    t2 = Math.imul(t2 ^ (t2 >>> 15), t2 | 1);
    t2 ^= t2 + Math.imul(t2 ^ (t2 >>> 7), t2 | 61);
    const u2 = ((t2 ^ (t2 >>> 14)) >>> 0) / 4294967296;
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  };
}

describe("singleIndexMetrics", () => {
  it("recovers known alpha and beta", () => {
    const rnd = seededNormal(2024);
    const n = 2000;
    const rM: number[] = [];
    const rI: number[] = [];
    const trueAlpha = 0.0002;
    const trueBeta = 1.25;
    for (let k = 0; k < n; k += 1) {
      const m = 0.0005 + 0.01 * rnd();
      const e = 0.005 * rnd();
      rM.push(m);
      rI.push(trueAlpha + trueBeta * m + e);
    }
    const fit = singleIndexMetrics(rI, rM);
    expect(fit.beta).toBeCloseTo(trueBeta, 2);
    expect(fit.alphaPerPeriod).toBeCloseTo(trueAlpha, 3);
    expect(fit.nObservations).toBe(n);
  });

  it("throws on shape mismatch", () => {
    expect(() => singleIndexMetrics([0, 1, 2], [0, 1])).toThrow(InvalidReturnWindowError);
  });

  it("throws on insufficient history", () => {
    expect(() => singleIndexMetrics([0], [0])).toThrow(InsufficientHistoryError);
  });

  it("throws on zero market variance", () => {
    expect(() =>
      singleIndexMetrics([0.01, 0.02, 0.03], [0.01, 0.01, 0.01]),
    ).toThrow(InvalidReturnWindowError);
  });

  it("throws on non-finite", () => {
    expect(() => singleIndexMetrics([0, NaN, 0], [0, 0, 1])).toThrow(InvalidReturnWindowError);
  });

  it("handles collinear r_i = β·r_M (σ²(e) ≈ 0)", () => {
    const rM = Array.from({ length: 500 }, (_, k) => Math.sin(k) * 0.01);
    const beta = 1.1;
    const rI = rM.map((m) => beta * m);
    const warnings: string[] = [];
    const fit = singleIndexMetrics(rI, rM, { warnings });
    expect(fit.beta).toBeCloseTo(beta, 10);
    expect(fit.alphaPerPeriod).toBeCloseTo(0, 12);
    expect(fit.firmSpecificVarPerPeriod).toBeGreaterThanOrEqual(0);
    expect(fit.firmSpecificVarPerPeriod).toBeLessThan(1e-10);
  });
});
