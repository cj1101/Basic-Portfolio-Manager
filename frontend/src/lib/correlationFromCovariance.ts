import type { CorrelationMatrix, CovarianceMatrix, OptimizationResult } from "@/types/contracts";

/**
 * Derives a correlation matrix from an annualized covariance matrix (ρᵢⱼ = Σᵢⱼ / (σᵢ σⱼ)).
 * Used when a cached or legacy `OptimizationResult` omits the `correlation` field.
 */
export function correlationFromCovariance(cov: CovarianceMatrix): CorrelationMatrix {
  const { tickers, matrix } = cov;
  const n = tickers.length;
  if (matrix.length !== n) {
    throw new Error("correlationFromCovariance: matrix row count does not match tickers");
  }
  const stdDevs: number[] = [];
  for (let i = 0; i < n; i += 1) {
    const v = matrix[i]?.[i];
    if (v == null || !Number.isFinite(v) || v <= 0) {
      throw new Error("correlationFromCovariance: non-positive or invalid diagonal variance");
    }
    stdDevs.push(Math.sqrt(v));
  }
  const out: number[][] = [];
  for (let i = 0; i < n; i += 1) {
    const row: number[] = [];
    for (let j = 0; j < n; j += 1) {
      const c = matrix[i]?.[j];
      if (c == null || !Number.isFinite(c)) {
        throw new Error("correlationFromCovariance: invalid covariance entry");
      }
      if (i === j) {
        row.push(1.0);
      } else {
        row.push(c / (stdDevs[i]! * stdDevs[j]!));
      }
    }
    out.push(row);
  }
  return { tickers: [...tickers], matrix: out };
}

/** Fills in `correlation` when the API or TanStack cache returns a legacy shape. */
export function ensureOptimizationResultHasCorrelation(
  r: OptimizationResult,
): OptimizationResult {
  if (r.correlation?.matrix != null && r.correlation.matrix.length > 0) {
    return r;
  }
  return { ...r, correlation: correlationFromCovariance(r.covariance) };
}
