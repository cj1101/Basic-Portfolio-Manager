/**
 * Sharpe ratio: `(E(r_p) − rᶠ) / σ_p`.
 */

export function sharpeRatio(
  expectedReturn: number,
  stdDev: number,
  riskFreeRate: number,
): number {
  if (!Number.isFinite(expectedReturn) || !Number.isFinite(stdDev) || !Number.isFinite(riskFreeRate)) {
    throw new Error("sharpeRatio received a non-finite input");
  }
  if (stdDev <= 0) {
    throw new Error(`stdDev must be strictly positive; got ${stdDev}`);
  }
  return (expectedReturn - riskFreeRate) / stdDev;
}
