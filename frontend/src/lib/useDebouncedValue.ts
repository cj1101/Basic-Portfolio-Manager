import { useEffect, useState } from "react";

/**
 * Returns `value` after it has remained unchanged for `delayMs`.
 *
 * Used by `PortfolioProvider` to avoid firing `/api/optimize` on every
 * keystroke when the user edits the ticker list, lookback window, or any of
 * the optimizer flags. The slider-driven `riskProfile` is intentionally NOT
 * routed through this — it only triggers client-side recomputation.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    if (delayMs <= 0) {
      setDebounced(value);
      return;
    }
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
