import { describe, expect, it } from "vitest";

import {
  OptimizerNonPsdCovarianceError,
  PSD_TOL,
  SYMMETRY_TOL,
  buildCovariance,
  ensurePsdCovariance,
  isPsd,
  isSymmetric,
  nearestPsd,
  solve,
  inverse,
  dot,
  matVec,
  quadForm,
} from "../src/index.js";

describe("buildCovariance", () => {
  it("recovers the Dataset A diagonal Σ", () => {
    const cov = buildCovariance(
      [0.15, 0.2, 0.3],
      [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
      ],
    );
    expect(cov[0]?.[0]).toBeCloseTo(0.0225, 12);
    expect(cov[1]?.[1]).toBeCloseTo(0.04, 12);
    expect(cov[2]?.[2]).toBeCloseTo(0.09, 12);
    expect(cov[0]?.[1]).toBe(0);
  });

  it("handles non-diagonal correlations", () => {
    const cov = buildCovariance(
      [0.2, 0.3],
      [
        [1, 0.4],
        [0.4, 1],
      ],
    );
    expect(cov[0]?.[0]).toBeCloseTo(0.04, 12);
    expect(cov[1]?.[1]).toBeCloseTo(0.09, 12);
    expect(cov[0]?.[1]).toBeCloseTo(0.2 * 0.3 * 0.4, 12);
    expect(cov[0]?.[1]).toBeCloseTo(cov[1]?.[0] ?? NaN, 12);
  });

  it("throws on shape mismatch", () => {
    expect(() => buildCovariance([0.1, 0.2], [[1]])).toThrow();
  });

  it("throws on negative std dev", () => {
    expect(() =>
      buildCovariance(
        [-0.1, 0.2],
        [
          [1, 0],
          [0, 1],
        ],
      ),
    ).toThrow();
  });
});

describe("isSymmetric / isPsd", () => {
  it("identifies identity as symmetric and PSD", () => {
    const eye = [
      [1, 0],
      [0, 1],
    ];
    expect(isSymmetric(eye)).toBe(true);
    expect(isPsd(eye)).toBe(true);
  });

  it("rejects asymmetric matrices", () => {
    expect(
      isSymmetric([
        [1, 0.5],
        [0, 1],
      ]),
    ).toBe(false);
  });

  it("detects non-PSD", () => {
    const m = [
      [1, 2],
      [2, 1],
    ];
    expect(isSymmetric(m)).toBe(true);
    expect(isPsd(m)).toBe(false);
  });
});

describe("nearestPsd", () => {
  it("leaves a PSD matrix unchanged", () => {
    const m = [
      [0.0225, 0, 0],
      [0, 0.04, 0],
      [0, 0, 0.09],
    ];
    const out = nearestPsd(m);
    expect(out[0]?.[0]).toBeCloseTo(0.0225, 12);
    expect(out[1]?.[1]).toBeCloseTo(0.04, 12);
    expect(out[2]?.[2]).toBeCloseTo(0.09, 12);
  });

  it("projects a slightly negative eigenvalue back to ≥ 0", () => {
    const m = [
      [-1e-10, 0],
      [0, 0.04],
    ];
    const out = nearestPsd(m);
    expect(out[0]?.[0] ?? NaN).toBeGreaterThanOrEqual(0);
  });
});

describe("ensurePsdCovariance", () => {
  it("returns a symmetrized copy for clean inputs", () => {
    const m = [
      [0.04, 0],
      [0, 0.09],
    ];
    const warnings: string[] = [];
    const out = ensurePsdCovariance(m, warnings);
    expect(out[0]?.[0]).toBeCloseTo(0.04, 12);
    expect(warnings.length).toBe(0);
  });

  it("projects minor drift with a warning", () => {
    const m = [
      [-PSD_TOL / 2, 0],
      [0, 0.09],
    ];
    const warnings: string[] = [];
    const out = ensurePsdCovariance(m, warnings);
    expect(warnings.length).toBe(1);
    expect(warnings[0]).toContain("projected to nearest PSD");
    expect(out).toBeDefined();
  });

  it("rejects asymmetric matrices", () => {
    const m = [
      [1, 0.5 + 10 * SYMMETRY_TOL],
      [0.5, 1],
    ];
    expect(() => ensurePsdCovariance(m)).toThrow(OptimizerNonPsdCovarianceError);
  });

  it("rejects materially non-PSD", () => {
    const m = [
      [1, 2],
      [2, 1],
    ];
    expect(() => ensurePsdCovariance(m)).toThrow(OptimizerNonPsdCovarianceError);
  });
});

describe("solve / inverse", () => {
  it("solves a diagonal system", () => {
    const x = solve(
      [
        [2, 0],
        [0, 3],
      ],
      [4, 9],
    );
    expect(x[0]).toBeCloseTo(2, 12);
    expect(x[1]).toBeCloseTo(3, 12);
  });

  it("handles row swapping (partial pivoting)", () => {
    const x = solve(
      [
        [0, 1],
        [1, 0],
      ],
      [3, 7],
    );
    expect(x[0]).toBeCloseTo(7, 12);
    expect(x[1]).toBeCloseTo(3, 12);
  });

  it("inverts correctly", () => {
    const inv = inverse([
      [2, 0],
      [0, 3],
    ]);
    expect(inv[0]?.[0]).toBeCloseTo(0.5, 12);
    expect(inv[1]?.[1]).toBeCloseTo(1 / 3, 12);
  });

  it("throws on singular", () => {
    expect(() =>
      solve(
        [
          [1, 1],
          [2, 2],
        ],
        [1, 2],
      ),
    ).toThrow();
  });
});

describe("dot / matVec / quadForm", () => {
  it("dot product of orthogonal vectors is zero", () => {
    expect(dot([1, 0], [0, 1])).toBe(0);
  });

  it("matVec", () => {
    const v = matVec(
      [
        [1, 2],
        [3, 4],
      ],
      [5, 6],
    );
    expect(v[0]).toBe(17);
    expect(v[1]).toBe(39);
  });

  it("quadForm", () => {
    expect(
      quadForm(
        [
          [1, 0],
          [0, 1],
        ],
        [3, 4],
      ),
    ).toBe(25);
  });

  it("throws on length mismatch", () => {
    expect(() => dot([1, 2], [1])).toThrow();
    expect(() => matVec([[1, 2]], [1])).toThrow();
  });
});
