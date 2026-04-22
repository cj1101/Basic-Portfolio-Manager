import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";
import type {
  OptimizationRequest,
  OptimizationResult,
  ReturnFrequency,
  RiskProfile,
  Ticker,
} from "@/types/contracts";
import { optimizationResultSample } from "@/fixtures/optimizationResultSample";
import {
  computeCompleteFromORP,
  type CompletePortfolioDerivation,
} from "@/lib/completePortfolio";
import { ensureOptimizationResultHasCorrelation } from "@/lib/correlationFromCovariance";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { useOptimization } from "@/lib/queries";
import type { ApiError } from "@/lib/api";

/**
 * Portfolio state for the dashboard.
 *
 * The React state owned by this provider is strictly *input* state:
 * `tickers`, `returnFrequency`, `lookbackYears`, `allowShort`,
 * `allowLeverage`, `riskProfile`. The *result* comes from
 * `useOptimization` (TanStack Query) and is cached on `(request body ∖
 * riskAversion)`. The `complete` field is always re-derived client-side
 * from the server-provided ORP + the live `riskProfile` using the utility
 * formula in `lib/completePortfolio.ts` — this is what makes the risk
 * slider feel instant without hitting the network.
 *
 * When the backend is unreachable (offline dev / early boot) the provider
 * falls back to the FIXTURES.md sample so the dashboard still renders
 * something useful. Control that with `VITE_USE_FIXTURE=1`.
 */

export type RequestStatus = "idle" | "loading" | "success" | "error";

export interface LivePortfolioResult extends OptimizationResult {
  complete: CompletePortfolioDerivation;
}

export interface PortfolioState {
  // --- inputs -------------------------------------------------------------
  tickers: Ticker[];
  returnFrequency: ReturnFrequency;
  lookbackYears: number;
  allowShort: boolean;
  allowLeverage: boolean;
  riskProfile: RiskProfile;

  // --- request lifecycle --------------------------------------------------
  status: RequestStatus;
  isFetching: boolean;
  error: ApiError | null;
  lastUpdatedAt: number | null;

  /** Live result used by every tab: latest server result with a live-derived complete. */
  result: LivePortfolioResult;
  /** True when `result` comes from the offline/demo fixture rather than the server. */
  isFallbackResult: boolean;

  // --- actions ------------------------------------------------------------
  addTicker: (t: Ticker) => void;
  removeTicker: (t: Ticker) => void;
  setTickers: (t: Ticker[]) => void;
  setReturnFrequency: (f: ReturnFrequency) => void;
  setLookbackYears: (n: number) => void;
  setAllowShort: (b: boolean) => void;
  setAllowLeverage: (b: boolean) => void;
  setRiskAversion: (a: number) => void;
  setTargetReturn: (r: number | undefined) => void;
  setRiskProfile: (profile: RiskProfile) => void;
  refetch: () => void;
  reset: () => void;
}

const PortfolioContext = createContext<PortfolioState | null>(null);

const TICKER_REGEX = /^[A-Z0-9.]{1,10}$/;

const normalizeTicker = (raw: string): string =>
  raw
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9.]/g, "");

const DEFAULT_TICKERS: Ticker[] = optimizationResultSample.stocks.map((s) => s.ticker);

const INITIAL_RISK_PROFILE: RiskProfile = {
  riskAversion: 3,
  targetReturn: 0.15,
};

const DEFAULT_FRONTIER_RESOLUTION = 40;
const DEBOUNCE_MS = 400;

const USE_FIXTURE_FALLBACK =
  import.meta.env?.VITE_USE_FIXTURE === "1" ||
  import.meta.env?.VITE_USE_FIXTURE === "true";

function buildRequest(state: {
  tickers: Ticker[];
  returnFrequency: ReturnFrequency;
  lookbackYears: number;
  allowShort: boolean;
  allowLeverage: boolean;
  riskProfile: RiskProfile;
}): OptimizationRequest {
  return {
    tickers: state.tickers,
    riskProfile: state.riskProfile,
    returnFrequency: state.returnFrequency,
    lookbackYears: state.lookbackYears,
    allowShort: state.allowShort,
    allowLeverage: state.allowLeverage,
    frontierResolution: DEFAULT_FRONTIER_RESOLUTION,
  };
}

export function PortfolioProvider({ children }: PropsWithChildren) {
  const [tickers, setTickersState] = useState<Ticker[]>([...DEFAULT_TICKERS]);
  const [returnFrequency, setReturnFrequency] = useState<ReturnFrequency>("daily");
  const [lookbackYears, setLookbackYearsState] = useState<number>(5);
  const [allowShort, setAllowShort] = useState<boolean>(true);
  const [allowLeverage, setAllowLeverage] = useState<boolean>(true);
  const [riskProfile, setRiskProfileState] = useState<RiskProfile>(INITIAL_RISK_PROFILE);

  // Only the fields that affect the server request are debounced. The risk
  // profile bypasses this — slider changes go straight into the request (so
  // the server's `complete` is consistent if refetched) but do NOT cause a
  // fresh network call because `riskAversion` is part of the query key only
  // for `complete` parity; see `queries.ts`. Client-side derivation below
  // re-runs on every render of `riskProfile`, giving instant visual feedback.
  const debouncedTickers = useDebouncedValue(tickers, DEBOUNCE_MS);
  const debouncedFrequency = useDebouncedValue(returnFrequency, DEBOUNCE_MS);
  const debouncedLookback = useDebouncedValue(lookbackYears, DEBOUNCE_MS);
  const debouncedAllowShort = useDebouncedValue(allowShort, DEBOUNCE_MS);
  const debouncedAllowLeverage = useDebouncedValue(allowLeverage, DEBOUNCE_MS);

  const request = useMemo(
    () =>
      buildRequest({
        tickers: debouncedTickers,
        returnFrequency: debouncedFrequency,
        lookbackYears: debouncedLookback,
        allowShort: debouncedAllowShort,
        allowLeverage: debouncedAllowLeverage,
        riskProfile,
      }),
    [
      debouncedTickers,
      debouncedFrequency,
      debouncedLookback,
      debouncedAllowShort,
      debouncedAllowLeverage,
      riskProfile,
    ],
  );

  const enabled = !USE_FIXTURE_FALLBACK && debouncedTickers.length >= 2;

  const query = useOptimization(request, { enabled });

  // Live-derive the Complete Portfolio from the current (server) ORP + the
  // *non-debounced* risk profile. This runs on every slider tick without
  // invalidating the query cache.
  const serverResult = query.data ?? null;

  const result = useMemo<LivePortfolioResult>(() => {
    const source =
      serverResult ??
      (USE_FIXTURE_FALLBACK || (!query.isLoading && !query.data)
        ? optimizationResultSample
        : null);
    if (source == null) {
      // While the first request is in-flight and we have no cached data, fall
      // back to the fixture so the charts remain stable. The consumers that
      // care about loading state should read `status === "loading"` and
      // render a skeleton instead.
      const fixture = ensureOptimizationResultHasCorrelation(optimizationResultSample);
      const complete = computeCompleteFromORP(fixture.orp, fixture.riskFreeRate, riskProfile);
      return { ...fixture, complete };
    }
    const normalized = ensureOptimizationResultHasCorrelation(source);
    const complete = computeCompleteFromORP(
      normalized.orp,
      normalized.riskFreeRate,
      riskProfile,
    );
    return { ...normalized, complete };
  }, [serverResult, riskProfile, query.isLoading, query.data]);

  const status: RequestStatus = query.isError
    ? "error"
    : query.isSuccess
      ? "success"
      : query.isLoading
        ? "loading"
        : "idle";

  const lastUpdatedAt =
    query.dataUpdatedAt && query.dataUpdatedAt > 0 ? query.dataUpdatedAt : null;

  const isFallbackResult = serverResult == null;

  // ---- actions -----------------------------------------------------------

  const addTicker = useCallback((raw: string) => {
    const t = normalizeTicker(raw);
    if (!t || !TICKER_REGEX.test(t)) return;
    setTickersState((prev) => (prev.includes(t) ? prev : [...prev, t]));
  }, []);

  const removeTicker = useCallback((t: Ticker) => {
    setTickersState((prev) => prev.filter((x) => x !== t));
  }, []);

  const setTickers = useCallback((next: Ticker[]) => {
    setTickersState(next.map(normalizeTicker).filter((t) => TICKER_REGEX.test(t)));
  }, []);

  const setLookbackYears = useCallback((n: number) => {
    const clamped = Math.max(1, Math.min(20, Math.round(n)));
    setLookbackYearsState(clamped);
  }, []);

  const setRiskAversion = useCallback((a: number) => {
    const clamped = Math.max(1, Math.min(10, Math.round(a)));
    setRiskProfileState((prev) => ({ ...prev, riskAversion: clamped }));
  }, []);

  const setTargetReturn = useCallback((r: number | undefined) => {
    setRiskProfileState((prev) => {
      if (r == null || !Number.isFinite(r)) {
        const { targetReturn: _drop, ...rest } = prev;
        return rest;
      }
      return { ...prev, targetReturn: r };
    });
  }, []);

  const setRiskProfile = useCallback((profile: RiskProfile) => {
    setRiskProfileState(profile);
  }, []);

  const refetch = useCallback(() => {
    void query.refetch();
  }, [query]);

  const reset = useCallback(() => {
    setTickersState([...DEFAULT_TICKERS]);
    setReturnFrequency("daily");
    setLookbackYearsState(5);
    setAllowShort(true);
    setAllowLeverage(true);
    setRiskProfileState(INITIAL_RISK_PROFILE);
  }, []);

  const value: PortfolioState = useMemo(
    () => ({
      tickers,
      returnFrequency,
      lookbackYears,
      allowShort,
      allowLeverage,
      riskProfile,
      status,
      isFetching: query.isFetching,
      error: (query.error as ApiError | null) ?? null,
      lastUpdatedAt,
      result,
      isFallbackResult,
      addTicker,
      removeTicker,
      setTickers,
      setReturnFrequency,
      setLookbackYears,
      setAllowShort,
      setAllowLeverage,
      setRiskAversion,
      setTargetReturn,
      setRiskProfile,
      refetch,
      reset,
    }),
    [
      tickers,
      returnFrequency,
      lookbackYears,
      allowShort,
      allowLeverage,
      riskProfile,
      status,
      query.isFetching,
      query.error,
      lastUpdatedAt,
      result,
      isFallbackResult,
      addTicker,
      removeTicker,
      setTickers,
      setLookbackYears,
      setRiskAversion,
      setTargetReturn,
      setRiskProfile,
      refetch,
      reset,
    ],
  );

  return <PortfolioContext.Provider value={value}>{children}</PortfolioContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePortfolio(): PortfolioState {
  const ctx = useContext(PortfolioContext);
  if (!ctx) {
    throw new Error("usePortfolio must be used within a <PortfolioProvider>");
  }
  return ctx;
}
