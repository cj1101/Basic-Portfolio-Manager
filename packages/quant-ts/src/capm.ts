/**
 * CAPM helpers (`.cursor/rules/quant.mdc` §5).
 *
 * - `r_CAPM = rᶠ + β · (E(r_M) − rᶠ)`
 * - `E(r_i) = r_CAPM + α_i`
 * - `σ²_i    = β² · σ²_M + σ²(e_i)`
 */

export function capmRequiredReturn(
  beta: number,
  marketExpectedReturn: number,
  riskFreeRate: number,
): number {
  return riskFreeRate + beta * (marketExpectedReturn - riskFreeRate);
}

export function capmTotalExpectedReturn(
  beta: number,
  alpha: number,
  marketExpectedReturn: number,
  riskFreeRate: number,
): number {
  return capmRequiredReturn(beta, marketExpectedReturn, riskFreeRate) + alpha;
}

export function capmSystematicVariance(beta: number, marketVariance: number): number {
  if (marketVariance < 0) {
    throw new Error(`marketVariance must be non-negative; got ${marketVariance}`);
  }
  return beta * beta * marketVariance;
}

export function capmTotalVariance(
  beta: number,
  marketVariance: number,
  firmSpecificVar: number,
): number {
  if (firmSpecificVar < 0) {
    throw new Error(`firmSpecificVar must be non-negative; got ${firmSpecificVar}`);
  }
  return capmSystematicVariance(beta, marketVariance) + firmSpecificVar;
}

export function capmTotalStdDev(
  beta: number,
  marketVariance: number,
  firmSpecificVar: number,
): number {
  return Math.sqrt(capmTotalVariance(beta, marketVariance, firmSpecificVar));
}
