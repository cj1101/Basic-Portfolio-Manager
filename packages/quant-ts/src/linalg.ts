/**
 * Linear-algebra primitives for `@portfolio/quant`.
 *
 * Hand-rolled so the math is dependency-free and deterministic across
 * environments. The routines are all sized for the portfolio-management use
 * case (n ≤ a few dozen) and favor clarity over micro-performance:
 *
 * - {@link solve}    — LU decomposition with partial pivoting.
 * - {@link inverse}  — solving against the identity.
 * - {@link symmetricEigenDecomposition} — Jacobi rotations; works for small
 *   dense symmetric matrices and terminates with off-diagonal < 1e-14 in a
 *   handful of sweeps.
 */

import { OptimizerNonPsdCovarianceError } from "./errors.js";

export const SYMMETRY_TOL = 1e-10;
export const PSD_TOL = 1e-8;
export const PROJECTION_FLOOR = 1e-12;

type Row = number[];
type Matrix = Row[];
/** Read-only 2D numeric grid; use for API inputs so callers are not forced to copy. */
type ReadonlyMatrix = readonly (readonly number[])[];

function dim(m: ReadonlyMatrix): { rows: number; cols: number } {
  const rows = m.length;
  const cols = rows === 0 ? 0 : (m[0]?.length ?? 0);
  for (const row of m) {
    if (row.length !== cols) throw new Error("matrix rows have inconsistent lengths");
  }
  return { rows, cols };
}

export function buildCovariance(
  stdDevs: readonly number[],
  correlation: readonly (readonly number[])[],
): Matrix {
  const n = stdDevs.length;
  if (correlation.length !== n) {
    throw new Error(`correlation must be (${n},${n}); got ${correlation.length} rows`);
  }
  for (const s of stdDevs) {
    if (!Number.isFinite(s) || s < 0) throw new Error("std_devs must be non-negative finite numbers");
  }
  const cov: Matrix = Array.from({ length: n }, () => new Array<number>(n).fill(0));
  for (let i = 0; i < n; i += 1) {
    const rowI = correlation[i];
    if (rowI === undefined || rowI.length !== n) {
      throw new Error(`correlation row ${i} must have length ${n}`);
    }
    const si = stdDevs[i] as number;
    const rowJ = correlation;
    for (let j = 0; j < n; j += 1) {
      const sj = stdDevs[j] as number;
      const rij = rowI[j] as number;
      const rji = (rowJ[j] as readonly number[])[i] as number;
      (cov[i] as Row)[j] = 0.5 * (si * sj * rij + si * sj * rji);
    }
  }
  return cov;
}

/** Maps covariance Σ to correlation ρ with ρᵢⱼ = Σᵢⱼ / (σᵢ σⱼ), unit diagonal. */
export function covarianceToCorrelation(cov: readonly (readonly number[])[]): Matrix {
  const d = safeDim(cov);
  if (!d || d.rows !== d.cols) {
    throw new Error("covariance_to_correlation requires a square 2D matrix");
  }
  const n = d.rows;
  const stdDevs: number[] = [];
  for (let i = 0; i < n; i += 1) {
    const v = (cov[i] as Row)[i] as number;
    if (!Number.isFinite(v) || v <= 0) {
      throw new Error("covariance diagonal variances must be positive finite for correlation");
    }
    stdDevs.push(Math.sqrt(v));
  }
  const rho: Matrix = Array.from({ length: n }, () => new Array<number>(n).fill(0));
  for (let i = 0; i < n; i += 1) {
    for (let j = 0; j < n; j += 1) {
      const c = (cov[i] as Row)[j] as number;
      const val = c / (stdDevs[i]! * stdDevs[j]!);
      (rho[i] as Row)[j] = i === j ? 1.0 : val;
    }
  }
  return symmetrize(rho);
}

export function isSymmetric(m: Matrix, tol: number = SYMMETRY_TOL): boolean {
  const d = safeDim(m);
  if (!d || d.rows !== d.cols) return false;
  for (let i = 0; i < d.rows; i += 1) {
    for (let j = i + 1; j < d.cols; j += 1) {
      const aij = (m[i] as Row)[j] as number;
      const aji = (m[j] as Row)[i] as number;
      if (Math.abs(aij - aji) > tol) return false;
    }
  }
  return true;
}

export function isPsd(m: Matrix, tol: number = PSD_TOL): boolean {
  if (!isSymmetric(m, Math.max(SYMMETRY_TOL, tol))) return false;
  const { values } = symmetricEigenDecomposition(symmetrize(m));
  const min = values.length === 0 ? 0 : Math.min(...values);
  return min >= -tol;
}

export function nearestPsd(m: Matrix, eps: number = PROJECTION_FLOOR): Matrix {
  const d = safeDim(m);
  if (!d || d.rows !== d.cols) throw new Error("nearest_psd requires a square 2D matrix");
  const sym = symmetrize(m);
  const { values, vectors } = symmetricEigenDecomposition(sym);
  const clipped = values.map((v) => Math.max(v, eps));
  const scaled = matMul(vectors, diagonal(clipped));
  const reconstructed = matMul(scaled, transpose(vectors));
  return symmetrize(reconstructed);
}

export function ensurePsdCovariance(m: Matrix, warnings?: string[]): Matrix {
  const d = safeDim(m);
  if (!d) {
    throw new OptimizerNonPsdCovarianceError("covariance matrix must be 2D", {});
  }
  if (d.rows !== d.cols) {
    throw new OptimizerNonPsdCovarianceError("covariance matrix must be square", {
      shape: [d.rows, d.cols],
    });
  }
  let maxAsym = 0;
  for (let i = 0; i < d.rows; i += 1) {
    for (let j = i + 1; j < d.cols; j += 1) {
      const diff = Math.abs((m[i] as Row)[j]! - (m[j] as Row)[i]!);
      if (diff > maxAsym) maxAsym = diff;
    }
  }
  if (maxAsym > SYMMETRY_TOL) {
    throw new OptimizerNonPsdCovarianceError("covariance matrix is not symmetric", {
      maxAsymmetry: maxAsym,
      tolerance: SYMMETRY_TOL,
    });
  }
  const sym = symmetrize(m);
  const { values } = symmetricEigenDecomposition(sym);
  const minEig = values.length === 0 ? 0 : Math.min(...values);

  if (minEig < -PSD_TOL) {
    throw new OptimizerNonPsdCovarianceError(
      "covariance matrix is materially non-PSD; refusing to project",
      { minEigenvalue: minEig, tolerance: PSD_TOL },
    );
  }
  if (minEig < 0) {
    warnings?.push(
      `covariance had minor PSD drift (minEigenvalue=${minEig.toExponential(3)}); projected to nearest PSD`,
    );
    return nearestPsd(sym);
  }
  return sym;
}

/**
 * Solve `A · x = b` using LU decomposition with partial pivoting.
 *
 * Raises on singular `A` (pivot magnitude below 1e-14).
 */
export function solve(a: Matrix, b: readonly number[]): number[] {
  const d = dim(a);
  if (d.rows !== d.cols) throw new Error("solve requires square A");
  if (b.length !== d.rows) throw new Error(`solve: b length ${b.length} != n ${d.rows}`);

  const n = d.rows;
  const lu: Matrix = a.map((row) => [...row]);
  const rhs = [...b];
  const piv = new Array<number>(n);
  for (let i = 0; i < n; i += 1) piv[i] = i;

  for (let k = 0; k < n; k += 1) {
    let maxAbs = Math.abs((lu[k] as Row)[k] as number);
    let maxRow = k;
    for (let i = k + 1; i < n; i += 1) {
      const v = Math.abs((lu[i] as Row)[k] as number);
      if (v > maxAbs) {
        maxAbs = v;
        maxRow = i;
      }
    }
    if (maxAbs < 1e-14) {
      throw new Error("singular matrix passed to solve()");
    }
    if (maxRow !== k) {
      const tmp = lu[k] as Row;
      lu[k] = lu[maxRow] as Row;
      lu[maxRow] = tmp;
      const tmpR = rhs[k] as number;
      rhs[k] = rhs[maxRow] as number;
      rhs[maxRow] = tmpR;
    }
    const pivot = (lu[k] as Row)[k] as number;
    for (let i = k + 1; i < n; i += 1) {
      const factor = ((lu[i] as Row)[k] as number) / pivot;
      (lu[i] as Row)[k] = factor;
      for (let j = k + 1; j < n; j += 1) {
        (lu[i] as Row)[j] = ((lu[i] as Row)[j] as number) - factor * ((lu[k] as Row)[j] as number);
      }
      rhs[i] = (rhs[i] as number) - factor * (rhs[k] as number);
    }
  }

  const x = new Array<number>(n).fill(0);
  for (let i = n - 1; i >= 0; i -= 1) {
    let s = rhs[i] as number;
    for (let j = i + 1; j < n; j += 1) {
      s -= ((lu[i] as Row)[j] as number) * (x[j] as number);
    }
    x[i] = s / ((lu[i] as Row)[i] as number);
  }
  return x;
}

export function inverse(a: Matrix): Matrix {
  const d = dim(a);
  if (d.rows !== d.cols) throw new Error("inverse requires square A");
  const n = d.rows;
  const inv: Matrix = Array.from({ length: n }, () => new Array<number>(n).fill(0));
  for (let i = 0; i < n; i += 1) {
    const e = new Array<number>(n).fill(0);
    e[i] = 1;
    const col = solve(a, e);
    for (let r = 0; r < n; r += 1) (inv[r] as Row)[i] = col[r] as number;
  }
  return inv;
}

export function matVec(a: Matrix, v: readonly number[]): number[] {
  const d = dim(a);
  if (d.cols !== v.length) {
    throw new Error(`matVec: matrix cols ${d.cols} != vec length ${v.length}`);
  }
  const out = new Array<number>(d.rows).fill(0);
  for (let i = 0; i < d.rows; i += 1) {
    let s = 0;
    const row = a[i] as Row;
    for (let j = 0; j < d.cols; j += 1) {
      s += (row[j] as number) * (v[j] as number);
    }
    out[i] = s;
  }
  return out;
}

export function dot(x: readonly number[], y: readonly number[]): number {
  if (x.length !== y.length) {
    throw new Error(`dot: length mismatch ${x.length} vs ${y.length}`);
  }
  let s = 0;
  for (let i = 0; i < x.length; i += 1) s += (x[i] as number) * (y[i] as number);
  return s;
}

export function quadForm(a: Matrix, v: readonly number[]): number {
  return dot(v, matVec(a, v));
}

export function sumVec(v: readonly number[]): number {
  let s = 0;
  for (const x of v) s += x;
  return s;
}

export function scaleVec(v: readonly number[], k: number): number[] {
  return v.map((x) => x * k);
}

/**
 * Jacobi cyclic symmetric eigendecomposition.
 *
 * Returns eigenvalues in an unsorted order (matches the Jacobi convention).
 * `vectors` contains the eigenvectors as columns:
 * `m · vectors[:, i] = values[i] · vectors[:, i]`.
 *
 * Convergence is tested against the sum of squared off-diagonal entries;
 * the loop exits once that falls below `1e-28 · (sum of squared diagonals)`
 * or after `max_sweeps` iterations — whichever comes first. For the matrix
 * sizes used in this project (n ≤ 30) it converges in < 50 sweeps.
 */
export function symmetricEigenDecomposition(m: Matrix, maxSweeps = 200): {
  values: number[];
  vectors: Matrix;
} {
  const d = dim(m);
  if (d.rows !== d.cols) throw new Error("eigendecomposition requires square A");
  const n = d.rows;
  const a: Matrix = m.map((row) => [...row]);
  const v: Matrix = Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => (i === j ? 1 : 0)),
  );

  for (let sweep = 0; sweep < maxSweeps; sweep += 1) {
    let off = 0;
    for (let p = 0; p < n - 1; p += 1) {
      for (let q = p + 1; q < n; q += 1) {
        off += ((a[p] as Row)[q] as number) ** 2;
      }
    }
    if (off < 1e-28) break;

    for (let p = 0; p < n - 1; p += 1) {
      for (let q = p + 1; q < n; q += 1) {
        const apq = (a[p] as Row)[q] as number;
        if (Math.abs(apq) < 1e-16) continue;
        const app = (a[p] as Row)[p] as number;
        const aqq = (a[q] as Row)[q] as number;
        const theta = (aqq - app) / (2 * apq);
        const t =
          theta >= 0
            ? 1 / (theta + Math.sqrt(1 + theta * theta))
            : 1 / (theta - Math.sqrt(1 + theta * theta));
        const c = 1 / Math.sqrt(1 + t * t);
        const s = t * c;

        (a[p] as Row)[p] = app - t * apq;
        (a[q] as Row)[q] = aqq + t * apq;
        (a[p] as Row)[q] = 0;
        (a[q] as Row)[p] = 0;

        for (let r = 0; r < n; r += 1) {
          if (r === p || r === q) continue;
          const arp = (a[r] as Row)[p] as number;
          const arq = (a[r] as Row)[q] as number;
          (a[r] as Row)[p] = c * arp - s * arq;
          (a[p] as Row)[r] = c * arp - s * arq;
          (a[r] as Row)[q] = s * arp + c * arq;
          (a[q] as Row)[r] = s * arp + c * arq;
        }
        for (let r = 0; r < n; r += 1) {
          const vrp = (v[r] as Row)[p] as number;
          const vrq = (v[r] as Row)[q] as number;
          (v[r] as Row)[p] = c * vrp - s * vrq;
          (v[r] as Row)[q] = s * vrp + c * vrq;
        }
      }
    }
  }

  const values = new Array<number>(n);
  for (let i = 0; i < n; i += 1) values[i] = (a[i] as Row)[i] as number;
  return { values, vectors: v };
}

function safeDim(m: ReadonlyMatrix): { rows: number; cols: number } | null {
  try {
    return dim(m);
  } catch {
    return null;
  }
}

function symmetrize(m: Matrix): Matrix {
  const { rows, cols } = dim(m);
  if (rows !== cols) throw new Error("symmetrize requires square");
  const out: Matrix = Array.from({ length: rows }, () => new Array<number>(cols).fill(0));
  for (let i = 0; i < rows; i += 1) {
    for (let j = 0; j < cols; j += 1) {
      (out[i] as Row)[j] = 0.5 * ((m[i] as Row)[j]! + (m[j] as Row)[i]!);
    }
  }
  return out;
}

function transpose(m: Matrix): Matrix {
  const { rows, cols } = dim(m);
  const out: Matrix = Array.from({ length: cols }, () => new Array<number>(rows).fill(0));
  for (let i = 0; i < rows; i += 1) {
    for (let j = 0; j < cols; j += 1) {
      (out[j] as Row)[i] = (m[i] as Row)[j] as number;
    }
  }
  return out;
}

function diagonal(values: readonly number[]): Matrix {
  const n = values.length;
  const out: Matrix = Array.from({ length: n }, () => new Array<number>(n).fill(0));
  for (let i = 0; i < n; i += 1) (out[i] as Row)[i] = values[i] as number;
  return out;
}

function matMul(a: Matrix, b: Matrix): Matrix {
  const ad = dim(a);
  const bd = dim(b);
  if (ad.cols !== bd.rows) {
    throw new Error(`matMul shape mismatch: (${ad.rows}x${ad.cols}) * (${bd.rows}x${bd.cols})`);
  }
  const out: Matrix = Array.from({ length: ad.rows }, () => new Array<number>(bd.cols).fill(0));
  for (let i = 0; i < ad.rows; i += 1) {
    const rowA = a[i] as Row;
    const outRow = out[i] as Row;
    for (let k = 0; k < ad.cols; k += 1) {
      const aik = rowA[k] as number;
      if (aik === 0) continue;
      const rowB = b[k] as Row;
      for (let j = 0; j < bd.cols; j += 1) {
        outRow[j] = (outRow[j] as number) + aik * (rowB[j] as number);
      }
    }
  }
  return out;
}

export const __internal = {
  symmetrize,
  matMul,
  transpose,
  diagonal,
};
