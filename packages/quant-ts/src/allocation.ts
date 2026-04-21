/**
 * Utility-maximizing allocation between the ORP and the risk-free asset —
 * TypeScript mirror of `backend/quant/allocation.py`.
 *
 * - `y* = (E(r_ORP) − rᶠ) / (A · σ²_ORP)`
 * - If `targetReturn > E(r_ORP)` → override with `y_target = (tr − rᶠ) / (E(r_ORP) − rᶠ)`.
 * - `allowLeverage === false` clamps `y_final` to 1.
 * - `y* < 0` raises `INVALID_RISK_PROFILE` (out of scope for v1).
 */

import { InvalidRiskProfileError } from "./errors.js";
import type { CompletePortfolio, ORP, RiskProfile } from "./types.js";

export interface UtilityMaxAllocationInput {
  orp: ORP;
  riskFreeRate: number;
  riskProfile: RiskProfile;
  allowLeverage: boolean;
  warnings?: string[];
}

export function utilityMaxAllocation(input: UtilityMaxAllocationInput): CompletePortfolio {
  const { orp, riskFreeRate, riskProfile, allowLeverage, warnings } = input;
  const rf = riskFreeRate;
  const eOrp = orp.expectedReturn;
  const varOrp = orp.variance;
  const sdOrp = orp.stdDev;
  const a = riskProfile.riskAversion;

  if (!Number.isFinite(rf) || !Number.isFinite(eOrp) || !Number.isFinite(varOrp)) {
    throw new InvalidRiskProfileError("non-finite inputs to allocation");
  }
  if (varOrp <= 0) {
    throw new InvalidRiskProfileError("ORP variance must be strictly positive", {
      variance: varOrp,
    });
  }
  if (a <= 0) {
    throw new InvalidRiskProfileError("risk_aversion must be strictly positive", { A: a });
  }

  const riskPremium = eOrp - rf;
  const yStarOptimal = riskPremium / (a * varOrp);

  if (yStarOptimal < 0) {
    throw new InvalidRiskProfileError(
      "optimal y* is negative — client would short the ORP; out of scope for v1",
      { yStar: yStarOptimal, riskPremium },
    );
  }

  let yFinal = yStarOptimal;

  if (riskProfile.targetReturn !== undefined) {
    const tr = riskProfile.targetReturn;
    if (tr > eOrp) {
      if (riskPremium <= 0) {
        throw new InvalidRiskProfileError(
          "cannot meet target_return: ORP has no risk premium over rᶠ",
          { targetReturn: tr, expectedReturn: eOrp, riskFree: rf },
        );
      }
      const yTarget = (tr - rf) / riskPremium;
      if (yTarget > yStarOptimal) {
        warnings?.push(
          `targetReturn=${tr.toFixed(6)} exceeds E(r_ORP)=${eOrp.toFixed(6)}; ` +
            `overriding y* from ${yStarOptimal.toFixed(6)} to y_target=${yTarget.toFixed(6)}`,
        );
        yFinal = yTarget;
      }
    }
  }

  if (!allowLeverage && yFinal > 1) {
    warnings?.push(`leverage disabled: clamping y from ${yFinal.toFixed(6)} to 1.000000`);
    yFinal = 1;
  }

  const leverageUsed = yFinal > 1;
  const weights: Record<string, number> = {};
  for (const [t, w] of Object.entries(orp.weights)) weights[t] = yFinal * w;
  const expectedReturn = rf + yFinal * riskPremium;
  const stdDev = yFinal * sdOrp;
  const weightRiskFree = 1 - yFinal;

  return {
    yStar: yFinal,
    weightRiskFree,
    weights,
    expectedReturn,
    stdDev,
    leverageUsed,
  };
}
