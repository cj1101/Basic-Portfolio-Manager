/**
 * Formatting helpers — the ONLY place in the frontend where annualized-decimal
 * values are converted to user-facing percent strings (per quant.mdc §1).
 */

/** Convert an annualized decimal (`0.123`) to a percent string (`"12.3%"`). */
export function pct(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Signed-percent — positive values get a "+" prefix. Useful for alpha / drift. */
export function signedPct(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const formatted = `${(value * 100).toFixed(decimals)}%`;
  return value > 0 ? `+${formatted}` : formatted;
}

/** Format a raw decimal (like Sharpe, beta) to fixed precision. */
export function decimals(value: number | null | undefined, precision = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(precision);
}

/** Format an integer with thousand separators. */
export function integer(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString("en-US");
}

/** Format a weight expressed as an annualized decimal. Negative weights (shorts) get explicit sign. */
export function weight(value: number | null | undefined, decimalsCount = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const formatted = `${(value * 100).toFixed(decimalsCount)}%`;
  if (value < 0) return `${formatted}`;
  return formatted;
}

/** Format an ISO datetime string to a short local-date display. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "—";
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
