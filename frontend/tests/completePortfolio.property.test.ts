/**
 * Property tests (fast-check) for `computeCompleteFromORP`.
 *
 * Invariants we assert for any well-formed input:
 *
 * 1. The weights on the N risky assets + the risk-free weight always sum to 1
 *    (± 1e-9). This is the fundamental CAL accounting identity.
 * 2. `leverageUsed` is true iff `yStar > 1 + 1e-9`.
 * 3. `expectedReturn = riskFreeRate + yStar * (E(r_ORP) - riskFreeRate)` to
 *    within a tight numerical tolerance.
 * 4. `stdDev = |yStar| * stdDev_ORP`.
 * 5. When `targetReturn > E(r_ORP)` and excess > 0, yStar ≥ the closed-form y*.
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { computeCompleteFromORP } from "@/lib/completePortfolio";
import type { ORP, RiskProfile } from "@/types/contracts";

function makeORP(n: number, weightsSeed: number[], expectedReturn: number, stdDev: number): ORP {
  const raw = weightsSeed.map((x) => Math.abs(x) + 1e-6);
  const total = raw.reduce((a, b) => a + b, 0);
  const weights: Record<string, number> = {};
  for (let i = 0; i < n; i++) {
    weights[`T${i}`] = raw[i]! / total;
  }
  return {
    weights,
    expectedReturn,
    stdDev,
    variance: stdDev ** 2,
    sharpe: (expectedReturn - 0) / stdDev,
  };
}

describe("computeCompleteFromORP — properties", () => {
  it("weights + weightRiskFree always sum to 1", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 2, max: 8 }),
        fc
          .float({
            min: Math.fround(0.08),
            max: Math.fround(0.4),
            noNaN: true,
            noDefaultInfinity: true,
          })
          .map((v) => Number(v)),
        fc
          .float({
            min: Math.fround(0.05),
            max: Math.fround(0.6),
            noNaN: true,
            noDefaultInfinity: true,
          })
          .map((v) => Number(v)),
        fc
          .float({
            min: Math.fround(0),
            max: Math.fround(0.06),
            noNaN: true,
            noDefaultInfinity: true,
          })
          .map((v) => Number(v)),
        fc.integer({ min: 1, max: 10 }),
        fc.array(
          fc.float({ min: Math.fround(0.01), max: Math.fround(5), noNaN: true }),
          { minLength: 2, maxLength: 8 },
        ),
        (n, eR, sd, rf, A, seedRaw) => {
          const seed =
            seedRaw.length >= n ? seedRaw.slice(0, n) : [...seedRaw, ...new Array(n - seedRaw.length).fill(1)];
          const orp = makeORP(n, seed, eR, sd);
          const profile: RiskProfile = { riskAversion: A };
          const result = computeCompleteFromORP(orp, rf, profile);
          const sum =
            Object.values(result.weights).reduce((a, b) => a + b, 0) + result.weightRiskFree;
          expect(sum).toBeCloseTo(1, 9);
        },
      ),
      { numRuns: 120 },
    );
  });

  it("expectedReturn and stdDev match the closed-form CAL identities", () => {
    fc.assert(
      fc.property(
        fc
          .float({ min: Math.fround(0.08), max: Math.fround(0.4), noNaN: true })
          .map((v) => Number(v)),
        fc
          .float({ min: Math.fround(0.08), max: Math.fround(0.6), noNaN: true })
          .map((v) => Number(v)),
        fc
          .float({ min: Math.fround(0), max: Math.fround(0.06), noNaN: true })
          .map((v) => Number(v)),
        fc.integer({ min: 1, max: 10 }),
        (eR, sd, rf, A) => {
          const orp = makeORP(2, [0.5, 0.5], eR, sd);
          const result = computeCompleteFromORP(orp, rf, { riskAversion: A });
          const excess = eR - rf;
          expect(result.expectedReturn).toBeCloseTo(rf + result.yStar * excess, 9);
          expect(result.stdDev).toBeCloseTo(Math.abs(result.yStar) * sd, 9);
          expect(result.leverageUsed).toBe(result.yStar > 1 + 1e-9);
        },
      ),
      { numRuns: 120 },
    );
  });

  it("targetReturn override never goes below the utility y*", () => {
    fc.assert(
      fc.property(
        fc
          .float({ min: Math.fround(0.12), max: Math.fround(0.3), noNaN: true })
          .map((v) => Number(v)),
        fc
          .float({ min: Math.fround(0.1), max: Math.fround(0.5), noNaN: true })
          .map((v) => Number(v)),
        fc
          .float({ min: Math.fround(0), max: Math.fround(0.05), noNaN: true })
          .map((v) => Number(v)),
        fc
          .float({ min: Math.fround(0.35), max: Math.fround(0.9), noNaN: true })
          .map((v) => Number(v)),
        fc.integer({ min: 4, max: 10 }),
        (eR, sd, rf, target, A) => {
          fc.pre(target > eR);
          const orp = makeORP(2, [0.5, 0.5], eR, sd);
          const result = computeCompleteFromORP(orp, rf, {
            riskAversion: A,
            targetReturn: target,
          });
          const excess = eR - rf;
          const closedForm = excess / (A * sd ** 2);
          const targetY = (target - rf) / excess;
          const expected = Math.max(closedForm, targetY);
          expect(result.yStar).toBeCloseTo(expected, 9);
        },
      ),
      { numRuns: 120 },
    );
  });
});
