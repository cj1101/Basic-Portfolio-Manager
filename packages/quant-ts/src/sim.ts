/**
 * Single-Index Model (SIM) regression.
 *
 * Per-asset (α, β, σ²(e)) estimated by OLS regression of asset excess
 * returns on market excess returns over the same window.
 *
 * Returns are expected to be per-period; the caller decides whether to
 * annualize α and σ²(e) with the correct factor. β is unit-less.
 */

import { InsufficientHistoryError, InvalidReturnWindowError } from "./errors.js";

export const CLAMP_FIRM_VAR_TOL = 1e-8;

export interface SingleIndexFit {
  alphaPerPeriod: number;
  beta: number;
  firmSpecificVarPerPeriod: number;
  nObservations: number;
}

export function singleIndexMetrics(
  returnsI: readonly number[],
  returnsM: readonly number[],
  options: { riskFreePerPeriod?: number; warnings?: string[] } = {},
): SingleIndexFit {
  if (returnsI.length !== returnsM.length) {
    throw new InvalidReturnWindowError("returnsI and returnsM must have matching lengths", {
      shapeI: returnsI.length,
      shapeM: returnsM.length,
    });
  }
  const n = returnsI.length;
  if (n < 2) {
    throw new InsufficientHistoryError(
      "need at least 2 observations for single-index regression",
      { nObservations: n },
    );
  }
  for (let k = 0; k < n; k += 1) {
    if (!Number.isFinite(returnsI[k] as number) || !Number.isFinite(returnsM[k] as number)) {
      throw new InvalidReturnWindowError("returns contain NaN or Inf");
    }
  }
  const rf = options.riskFreePerPeriod ?? 0;

  let meanI = 0;
  let meanM = 0;
  for (let k = 0; k < n; k += 1) {
    meanI += (returnsI[k] as number) - rf;
    meanM += (returnsM[k] as number) - rf;
  }
  meanI /= n;
  meanM /= n;

  let covIM = 0;
  let varM = 0;
  let varI = 0;
  for (let k = 0; k < n; k += 1) {
    const di = ((returnsI[k] as number) - rf) - meanI;
    const dm = ((returnsM[k] as number) - rf) - meanM;
    covIM += di * dm;
    varM += dm * dm;
    const dRaw = (returnsI[k] as number) - (meanI + rf);
    varI += dRaw * dRaw;
  }
  const denom = n - 1;
  covIM /= denom;
  varM /= denom;
  varI /= denom;

  if (varM <= 0) {
    throw new InvalidReturnWindowError(
      "market excess returns have zero variance; cannot fit beta",
      { marketVariance: varM },
    );
  }

  const beta = covIM / varM;
  const alpha = meanI - beta * meanM;

  let firmVar = varI - beta * beta * varM;
  if (firmVar < 0) {
    if (firmVar < -CLAMP_FIRM_VAR_TOL) {
      throw new InvalidReturnWindowError(
        "firm-specific variance strongly negative; input data is pathological",
        { firmSpecificVar: firmVar, tolerance: CLAMP_FIRM_VAR_TOL },
      );
    }
    options.warnings?.push(
      `firm_specific_var had minor negative drift (${firmVar.toExponential(3)}); clamped to 0`,
    );
    firmVar = 0;
  }

  return {
    alphaPerPeriod: alpha,
    beta,
    firmSpecificVarPerPeriod: firmVar,
    nObservations: n,
  };
}
