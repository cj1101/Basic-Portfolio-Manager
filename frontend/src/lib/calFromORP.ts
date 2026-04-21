import type { CALPoint, ORP } from "@/types/contracts";

/**
 * Generate CAL points from (0, r_f) through (σ_ORP, E(r_ORP)) out to y = yMax.
 * This is purely a display helper — the line is straight so two endpoints
 * suffice to draw it, but we emit multiple points so the mouse-hover tooltip
 * is useful.
 *
 * A point on the CAL for a given `y` has:
 *   σ_p(y)   = y · σ_ORP
 *   E(r_p)(y) = r_f + y · (E(r_ORP) - r_f)
 */
export function calFromORP(
  orp: ORP,
  riskFreeRate: number,
  options: { yMax?: number; steps?: number } = {},
): CALPoint[] {
  const yMax = options.yMax ?? 1.6;
  const steps = options.steps ?? 16;

  const points: CALPoint[] = [];
  const excess = orp.expectedReturn - riskFreeRate;

  for (let i = 0; i <= steps; i += 1) {
    const y = (yMax * i) / steps;
    points.push({
      y,
      stdDev: y * orp.stdDev,
      expectedReturn: riskFreeRate + y * excess,
    });
  }
  return points;
}

/** Map a `y` value to its point on the CAL. */
export function pointAt(orp: ORP, riskFreeRate: number, y: number): CALPoint {
  const excess = orp.expectedReturn - riskFreeRate;
  return {
    y,
    stdDev: y * orp.stdDev,
    expectedReturn: riskFreeRate + y * excess,
  };
}
