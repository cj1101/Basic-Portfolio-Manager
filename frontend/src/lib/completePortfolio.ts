import type { CompletePortfolio, ORP, RiskProfile, Ticker } from "@/types/contracts";

/**
 * Pure, display-layer recompute of the `CompletePortfolio` from a known ORP
 * and a live `RiskProfile`. This is NOT the optimizer: the ORP weights and
 * its moments are taken as given. We just apply the utility-max formula and
 * the target-return leverage override from `.cursor/rules/quant.mdc` §4.
 *
 *   y*       = (E(r_ORP) - r_f) / (A * σ²_ORP)
 *   y_target = (targetReturn - r_f) / (E(r_ORP) - r_f)     (only if targetReturn > E(r_ORP))
 *   y        = max(y*, y_target)
 *
 * The returned complete weights equal `y * w_ORP` for each risky asset;
 * `weightRiskFree = 1 - y` (can be negative when leverage is used).
 *
 * This function is imported by the React context AND by tests. It has no
 * React / DOM dependencies on purpose.
 */
export interface CompletePortfolioDerivation extends CompletePortfolio {
  /** True when the target-return override pushed `y` beyond the utility-max `y*`. */
  targetReturnOverride: boolean;
  /** The raw utility-max y* before any override. */
  yUtility: number;
  /** The target-return y, or null when `targetReturn` is not set / below E(r_ORP). */
  yTarget: number | null;
}

export function computeCompleteFromORP(
  orp: ORP,
  riskFreeRate: number,
  riskProfile: RiskProfile,
): CompletePortfolioDerivation {
  const { riskAversion, targetReturn } = riskProfile;

  if (!Number.isFinite(riskAversion) || riskAversion < 1 || riskAversion > 10) {
    throw new Error(`riskAversion must be an integer in [1, 10]; got ${riskAversion}`);
  }
  if (orp.variance <= 0) {
    throw new Error(`ORP variance must be positive; got ${orp.variance}`);
  }

  const excess = orp.expectedReturn - riskFreeRate;
  const yUtility = excess / (riskAversion * orp.variance);

  let y = yUtility;
  let yTarget: number | null = null;
  let targetReturnOverride = false;

  if (targetReturn != null && Number.isFinite(targetReturn) && targetReturn > orp.expectedReturn) {
    if (excess <= 0) {
      // Risk-free exceeds ORP — leverage can't get you to targetReturn.
      // Phase 1 just leaves y at yUtility; math layer will raise a typed error.
      yTarget = null;
    } else {
      yTarget = (targetReturn - riskFreeRate) / excess;
      if (yTarget > yUtility) {
        y = yTarget;
        targetReturnOverride = true;
      }
    }
  }

  const weights: Record<Ticker, number> = {};
  for (const [ticker, w] of Object.entries(orp.weights)) {
    weights[ticker] = y * w;
  }

  // σ_complete = |y| · σ_ORP (positive y in this project — v1 rejects negative y).
  const stdDev = Math.abs(y) * orp.stdDev;
  const expectedReturn = riskFreeRate + y * excess;

  return {
    yStar: y,
    weightRiskFree: 1 - y,
    weights,
    expectedReturn,
    stdDev,
    leverageUsed: y > 1 + 1e-9,
    targetReturnOverride,
    yUtility,
    yTarget,
  };
}
