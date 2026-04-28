import { useState, useCallback, useEffect, useMemo } from "react";
import { usePortfolio } from "@/state/portfolioContext";
import { useHistoricalBulk } from "@/lib/queries";
import { MovingAverageChart } from "../charts/MovingAverageChart";
import { RelativeStrengthChart } from "../charts/RelativeStrengthChart";
import { TechnicalWriteUp } from "./TechnicalWriteUp";
import { postValuation, ApiError } from "@/lib/api";
import type { HistoricalResponse, ValuationResult } from "@/types/contracts";
import { Loader2 } from "lucide-react";

// ---- valuation retry logic (mirrors CourseMetricsTab) ----
const VALUATION_MAX_ATTEMPTS = 45;
const VALUATION_RETRY_DELAY_MS = 1000;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isThrottleError(e: unknown): boolean {
  if (!(e instanceof ApiError)) return false;
  if (e.status === 429 || e.status === 503) return true;
  if (e.code === "DATA_PROVIDER_UNAVAILABLE" || e.code === "DATA_PROVIDER_RATE_LIMIT") return true;
  const m = e.message.toLowerCase();
  return (
    m.includes("alpha vantage") ||
    m.includes("rate limit") ||
    m.includes("sparingly") ||
    m.includes("try again shortly")
  );
}

export interface TechnicalAnalysisTabProps {
  onTechnicalDataLoaded?: (payload: {
    selectedTicker: string;
    stockDataMap: Record<string, HistoricalResponse>;
    benchmark: HistoricalResponse;
  } | null) => void;
  onValuationLoaded?: (valuation: ValuationResult | null) => void;
}

export function TechnicalAnalysisTab({
  onTechnicalDataLoaded,
  onValuationLoaded,
}: TechnicalAnalysisTabProps) {
  const { tickers, optimizationRequest } = usePortfolio();

  // Ticker selected for the interactive charts
  const [selectedTicker, setSelectedTicker] = useState<string>(tickers[0] || "");

  // Lifted MA window size so the write-up can reference the same value
  const [maWindowSize, setMaWindowSize] = useState<number>(50);

  // Valuation state
  const [valuation, setValuation] = useState<ValuationResult | null>(null);
  const [valuationLoading, setValuationLoading] = useState(false);
  const [valuationErr, setValuationErr] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Historical price data for all tickers + SPY benchmark
  const allTickers = Array.from(new Set([...tickers, "SPY"]));
  const queries = useHistoricalBulk(
    allTickers,
    // Technical charts are always computed from daily bars so the
    // moving-average window remains a true day count across modes.
    "daily",
    optimizationRequest.lookbackYears ?? 5,
    optimizationRequest.asOf,
  );

  const isLoading = queries.some((q) => q.isLoading);
  const isError = queries.some((q) => q.isError);

  const stockData = queries.find((q) => q.data?.ticker === selectedTicker)?.data?.bars || [];
  const benchmarkData = queries.find((q) => q.data?.ticker === "SPY")?.data?.bars || [];

  // Build a map of ticker → bars for the write-up
  const stockDataMap: Record<string, typeof stockData> = {};
  for (const ticker of tickers) {
    stockDataMap[ticker] = queries.find((q) => q.data?.ticker === ticker)?.data?.bars || [];
  }
  const technicalHistoryPayload = useMemo<Record<string, HistoricalResponse> | null>(() => {
    if (isLoading || isError) return null;
    const entries: Array<readonly [string, HistoricalResponse]> = [];
    for (const ticker of tickers) {
      const query = queries.find((q) => q.data?.ticker === ticker);
      if (query?.data) {
        entries.push([ticker, query.data] as const);
      }
    }
    if (entries.length !== tickers.length) return null;
    return Object.fromEntries(entries);
  }, [isError, isLoading, queries, tickers]);

  const benchmarkPayload = useMemo<HistoricalResponse | null>(() => {
    if (isLoading || isError) return null;
    return queries.find((q) => q.data?.ticker === "SPY")?.data ?? null;
  }, [isError, isLoading, queries]);

  useEffect(() => {
    if (!technicalHistoryPayload || !benchmarkPayload) {
      onTechnicalDataLoaded?.(null);
      return;
    }
    onTechnicalDataLoaded?.({
      selectedTicker,
      stockDataMap: technicalHistoryPayload,
      benchmark: benchmarkPayload,
    });
  }, [
    benchmarkPayload,
    onTechnicalDataLoaded,
    selectedTicker,
    technicalHistoryPayload,
  ]);

  useEffect(() => {
    onValuationLoaded?.(valuation);
  }, [onValuationLoaded, valuation]);

  const loadValuation = useCallback(async () => {
    setValuationErr(null);
    setValuationLoading(true);
    setAttempt(0);
    const body = {
      tickers,
      ddmGordonG: 0.03,
      ddmTwoStage: { g1: 0.08, g2: 0.03, nPeriods: 5 },
      wacc: 0.09,
      fcffGrowth: 0.02,
      fcffTerminalGrowth: 0.02,
      ...(optimizationRequest.asOf ? { asOf: optimizationRequest.asOf } : {}),
    };
    try {
      for (let i = 1; i <= VALUATION_MAX_ATTEMPTS; i++) {
        setAttempt(i);
        try {
          const res = await postValuation(body);
          setValuation(res);
          return;
        } catch (e) {
          if (!isThrottleError(e) || i >= VALUATION_MAX_ATTEMPTS) {
            setValuationErr(
              e instanceof ApiError ? e.message : "Valuation failed — fundamentals unavailable",
            );
            return;
          }
          await delay(VALUATION_RETRY_DELAY_MS);
        }
      }
    } finally {
      setValuationLoading(false);
      setAttempt(0);
    }
  }, [tickers, optimizationRequest.asOf]);

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Technical Analysis</h2>
        <p className="mt-1 text-sm text-slate-600">
          Visualize trends and momentum relative to the S&amp;P 500 benchmark, then read the
          auto-generated portfolio analysis write-up below.
        </p>
      </div>

      {/* Ticker selector */}
      <div className="flex items-center gap-4">
        <label htmlFor="ticker-select" className="text-sm font-medium text-slate-700">
          Select Firm:
        </label>
        <select
          id="ticker-select"
          value={selectedTicker}
          onChange={(e) => setSelectedTicker(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          {tickers.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {/* Charts */}
      {isLoading ? (
        <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-8 justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
          <p className="text-sm font-medium text-slate-700">Loading historical data…</p>
        </div>
      ) : isError ? (
        <div className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Failed to load historical data for one or more tickers.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-8">
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <MovingAverageChart
              bars={stockData}
              ticker={selectedTicker}
              height={400}
              windowSize={maWindowSize}
              onWindowSizeChange={setMaWindowSize}
            />
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <RelativeStrengthChart
              stockBars={stockData}
              benchmarkBars={benchmarkData}
              stockTicker={selectedTicker}
              benchmarkTicker="SPY"
              height={300}
            />
          </div>
        </div>
      )}

      {/* Valuation retry status */}
      {valuationLoading && (
        <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 shadow-sm">
          <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-brand-600" />
          <div>
            <p className="font-medium text-slate-900">
              {attempt > 1 ? "Alpha Vantage throttled — retrying…" : "Loading valuation data…"}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              Attempt {Math.max(1, attempt)} of {VALUATION_MAX_ATTEMPTS}. Fetching fundamentals for
              each ticker.
            </p>
          </div>
        </div>
      )}

      {valuationErr && (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {valuationErr}
        </p>
      )}

      {/* Write-up */}
      <TechnicalWriteUp
        tickers={tickers}
        stockDataMap={stockDataMap}
        benchmarkBars={benchmarkData}
        windowSize={maWindowSize}
        valuation={valuation}
        valuationLoading={valuationLoading}
        onLoadValuation={loadValuation}
      />
    </div>
  );
}
