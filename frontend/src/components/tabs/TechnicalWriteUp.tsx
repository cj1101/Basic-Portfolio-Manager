import { useMemo } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import type { PriceBar, ValuationResult, TickerValuationBlock } from "@/types/contracts";

// ---------------------------------------------------------------------------
// Company name lookup
// ---------------------------------------------------------------------------
const TICKER_NAMES: Record<string, string> = {
  IBM: "International Business Machines Corp.",
  AAOI: "Applied Optoelectronics, Inc.",
  AAPL: "Apple Inc.",
  MSFT: "Microsoft Corporation",
  GOOGL: "Alphabet Inc.",
  GOOG: "Alphabet Inc.",
  AMZN: "Amazon.com, Inc.",
  META: "Meta Platforms, Inc.",
  NVDA: "NVIDIA Corporation",
  TSLA: "Tesla, Inc.",
  JPM: "JPMorgan Chase & Co.",
  BAC: "Bank of America Corporation",
  WFC: "Wells Fargo & Company",
  GS: "The Goldman Sachs Group, Inc.",
  JNJ: "Johnson & Johnson",
  PFE: "Pfizer Inc.",
  XOM: "Exxon Mobil Corporation",
  CVX: "Chevron Corporation",
  PG: "The Procter & Gamble Company",
  KO: "The Coca-Cola Company",
  AMGN: "Amgen Inc.",
  SPY: "SPDR S&P 500 ETF",
  QQQ: "Invesco QQQ Trust",
  INTC: "Intel Corporation",
  AMD: "Advanced Micro Devices, Inc.",
  QCOM: "QUALCOMM Incorporated",
};

function name(ticker: string): string {
  return TICKER_NAMES[ticker] ?? ticker;
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------
function fmtPct(x: number | null | undefined, decimals = 2): string {
  if (x == null || !isFinite(x)) return "[—]";
  return `${(x * 100).toFixed(decimals)}%`;
}
function fmtUsd(x: number | null | undefined, decimals = 2): string {
  if (x == null || !isFinite(x)) return "[—]";
  return `$${x.toFixed(decimals)}`;
}
function fmtNum(x: number | null | undefined, decimals = 2): string {
  if (x == null || !isFinite(x)) return "[—]";
  return x.toFixed(decimals);
}
function fmtDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (isNaN(d.valueOf())) return dateStr;
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

// ---------------------------------------------------------------------------
// Analysis helpers
// ---------------------------------------------------------------------------
interface RSStats {
  volatilityProfile: "low" | "moderate" | "high";
  trend: "outperforming" | "underperforming" | "flat";
  cv: number;
}

function computeRSStats(stockBars: PriceBar[], benchmarkBars: PriceBar[]): RSStats | null {
  const bMap = new Map(benchmarkBars.map((b) => [b.date, b.close]));
  const ratios: number[] = [...stockBars]
    .sort((a, b) => a.date.localeCompare(b.date))
    .flatMap((bar) => {
      const bench = bMap.get(bar.date);
      return bench && bench > 0 ? [bar.close / bench] : [];
    });
  if (ratios.length < 20) return null;
  const mean = ratios.reduce((s, r) => s + r, 0) / ratios.length;
  const variance = ratios.reduce((s, r) => s + (r - mean) ** 2, 0) / ratios.length;
  const cv = Math.sqrt(variance) / mean;
  const first = ratios[0]!;
  const last = ratios[ratios.length - 1]!;
  const delta = Math.abs(last - first) / first;
  const trend = delta < 0.05 ? "flat" : last > first ? "outperforming" : "underperforming";
  const volatilityProfile: RSStats["volatilityProfile"] =
    cv > 0.18 ? "high" : cv > 0.08 ? "moderate" : "low";
  return { cv, trend, volatilityProfile };
}

interface MAStats {
  totalCrossovers: number;
  bullishCount: number;
  bearishCount: number;
  firstBullish: string | null;
  firstBearish: string | null;
  hugsMA: boolean; // true = low avg spread
}

function computeMAStats(bars: PriceBar[], windowSize: number): MAStats {
  const sorted = [...bars].sort((a, b) => a.date.localeCompare(b.date));
  const crossovers: { date: string; type: "bullish" | "bearish" }[] = [];
  const spreads: number[] = [];
  let prevOver: boolean | null = null;

  for (let i = 0; i < sorted.length; i++) {
    if (i < windowSize - 1) continue;
    let sum = 0;
    for (let j = 0; j < windowSize; j++) sum += sorted[i - j]!.close;
    const ma = sum / windowSize;
    const price = sorted[i]!.close;
    spreads.push(Math.abs(price - ma) / ma);
    const over = price > ma;
    if (prevOver !== null && over !== prevOver) {
      crossovers.push({ date: sorted[i]!.date, type: over ? "bullish" : "bearish" });
    }
    prevOver = over;
  }

  const avgSpread = spreads.length ? spreads.reduce((s, x) => s + x, 0) / spreads.length : 0;
  return {
    totalCrossovers: crossovers.length,
    bullishCount: crossovers.filter((c) => c.type === "bullish").length,
    bearishCount: crossovers.filter((c) => c.type === "bearish").length,
    firstBullish: crossovers.find((c) => c.type === "bullish")?.date ?? null,
    firstBearish: crossovers.find((c) => c.type === "bearish")?.date ?? null,
    hugsMA: avgSpread < 0.05,
  };
}

function getCurrentPrice(bars: PriceBar[]): number | null {
  if (!bars.length) return null;
  const sorted = [...bars].sort((a, b) => b.date.localeCompare(a.date));
  return sorted[0]!.close;
}

function classifyValuation(
  currentPrice: number | null,
  ddmGordon: number | null | undefined,
): "undervalued" | "overvalued" | "fairly priced" | null {
  if (!currentPrice || !ddmGordon || !isFinite(ddmGordon)) return null;
  const ratio = ddmGordon / currentPrice;
  if (ratio > 1.05) return "undervalued";
  if (ratio < 0.95) return "overvalued";
  return "fairly priced";
}

function isGrowthProfile(v: TickerValuationBlock): boolean {
  const beta = v.calculatedBeta;
  const hasDDM = v.ddmGordon != null && isFinite(v.ddmGordon) && v.ddmGordon > 0;
  if (!hasDDM && beta != null && beta > 1.3) return true;
  if (hasDDM && (beta == null || beta < 1.3)) return false;
  return !hasDDM;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function SectionHeader({ num, title }: { num: string; title: string }) {
  return (
    <div className="flex items-baseline gap-3 mb-3 mt-8 first:mt-0">
      <span className="shrink-0 rounded bg-brand-600 px-2 py-0.5 text-xs font-bold text-white">
        §{num}
      </span>
      <h3 className="text-base font-bold text-slate-900">{title}</h3>
    </div>
  );
}

function Val({ children }: { children: React.ReactNode }) {
  return <strong className="text-brand-700">{children}</strong>;
}

function Missing() {
  return (
    <span className="rounded bg-amber-100 px-1 text-xs font-mono text-amber-700">
      [load valuation ↓]
    </span>
  );
}

function Placeholder({ label }: { label: string }) {
  return (
    <span className="rounded bg-amber-100 px-1 text-xs font-mono text-amber-700">[{label}]</span>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
export interface TechnicalWriteUpProps {
  tickers: string[];
  stockDataMap: Record<string, PriceBar[]>;
  benchmarkBars: PriceBar[];
  windowSize: number;
  valuation: ValuationResult | null;
  valuationLoading: boolean;
  onLoadValuation: () => void;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export function TechnicalWriteUp({
  tickers,
  stockDataMap,
  benchmarkBars,
  windowSize,
  valuation,
  valuationLoading,
  onLoadValuation,
}: TechnicalWriteUpProps) {
  // Pre-compute per-ticker stats so prose can reference them inline
  const stats = useMemo(() => {
    return tickers.map((ticker) => {
      const bars = stockDataMap[ticker] ?? [];
      const rs = computeRSStats(bars, benchmarkBars);
      const ma = computeMAStats(bars, windowSize);
      const currentPrice = getCurrentPrice(bars);
      const val = valuation?.perTicker.find((v) => v.ticker === ticker) ?? null;
      const valClass = val ? classifyValuation(currentPrice, val.ddmGordon) : null;
      const growth = val ? isGrowthProfile(val) : null;
      return { ticker, bars, rs, ma, currentPrice, val, valClass, growth };
    });
  }, [tickers, stockDataMap, benchmarkBars, windowSize, valuation]);

  const hasValuation = valuation != null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-6 py-4">
        <div>
          <h2 className="text-base font-bold text-slate-900">Portfolio Analysis Write-Up</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Dynamic narrative — values auto-populated from live data
          </p>
        </div>
        {!hasValuation && (
          <button
            type="button"
            onClick={onLoadValuation}
            disabled={valuationLoading}
            className="flex items-center gap-2 rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
          >
            {valuationLoading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading valuation…
              </>
            ) : (
              <>
                <AlertCircle className="h-3.5 w-3.5" /> Load Valuation Data to Fill §4
              </>
            )}
          </button>
        )}
      </div>

      <div className="px-6 py-5 text-sm leading-relaxed text-slate-700 space-y-1">
        {/* ================================================================
            SECTION 4
        ================================================================ */}
        <SectionHeader num="4" title="Common Stock Valuation and Earnings Analysis" />
<h3 className="text-base font-semibold text-slate-900 mt-4">Common Stock Valuation</h3>

        <SectionHeader num="4.1" title="Common Stock Valuation" />

        <p>
          To estimate the intrinsic value of our portfolio holdings, we applied multiple valuation
          frameworks, recognizing that the distinct nature of our{" "}
          <Val>{tickers.length}</Val>-firm portfolio requires different modeling approaches.
        </p>

        {stats.map(({ ticker, val, valClass, growth, currentPrice }, i) => {
          const isGrowth = growth ?? (!val?.ddmGordon);
          const prevTickers = tickers.slice(0, i);
          return (
            <div key={ticker} className="mt-4 pl-4 border-l-2 border-slate-100">
              <p className="font-semibold text-slate-800 mb-1">
                {name(ticker)} ({ticker})
              </p>

              {!isGrowth ? (
                <>
                  <p>
                    As a {val?.calculatedBeta != null && val.calculatedBeta < 0.8 ? "low-beta, " : ""}
                    established firm, {ticker} boasts a consistent history of returning capital to
                    shareholders, making it an ideal candidate for dividend-based valuation.
                  </p>
                  <p className="mt-2">
                    <strong>Historical &amp; Sustainable Growth:</strong> We calculated {ticker}
                    {"'"}s historical dividend growth rate (<em>g</em>) at{" "}
                    {val ? <Val>{fmtPct(val.historicalGrowthRate)}</Val> : <Missing />}. To
                    cross-reference this, we determined the Sustainable Growth Rate (SGR) using the
                    firm&apos;s retention ratio and Return on Equity (ROE of{" "}
                    {val ? <Val>{fmtPct(val.roe)}</Val> : <Missing />}), yielding an SGR of{" "}
                    {val ? <Val>{fmtPct(val.sustainableGrowthRate)}</Val> : <Missing />}.
                  </p>
                  <p className="mt-2">
                    <strong>Dividend Discount Models:</strong> Applying the constant growth Dividend
                    Discount Model (V₀ = D₁ ∕ (k − g)), we calculated a current intrinsic value of{" "}
                    {val ? <Val>{fmtUsd(val.ddmGordon)}</Val> : <Missing />} for {ticker}.
                    Recognizing that growth may not be strictly linear, we also applied a Two-Stage
                    Dividend Growth Model. This yielded a two-stage intrinsic value of{" "}
                    {val ? <Val>{fmtUsd(val.ddmTwoStage)}</Val> : <Missing />}. Compared to its
                    current market price of{" "}
                    <Val>{currentPrice ? fmtUsd(currentPrice) : "[—]"}</Val>, {ticker} appears to
                    be{" "}
                    {valClass ? (
                      <Val>{valClass}</Val>
                    ) : (
                      <Placeholder label="undervalued / overvalued / fairly priced" />
                    )}
                    .
                  </p>
                </>
              ) : (
                <>
                  <p>
                    {prevTickers.length > 0
                      ? `Unlike ${prevTickers.join(" and ")}, `
                      : ""}
                    {ticker} is a{" "}
                    {val?.calculatedBeta != null && val.calculatedBeta > 1.3 ? "high-beta " : ""}
                    growth-oriented firm that does not pay a regular dividend, rendering the
                    traditional Dividend Discount Model inapplicable.
                  </p>
                  <p className="mt-2">
                    <strong>Price-Ratio Analysis:</strong> Instead, we relied on price-ratio
                    analysis to estimate {ticker}&apos;s relative valuation. The market currently
                    prices {ticker} at a P/E of{" "}
                    {val ? <Val>{fmtNum(val.priceToEarnings)}</Val> : <Missing />}, a P/B of{" "}
                    {val ? <Val>{fmtNum(val.priceToBook)}</Val> : <Missing />}, and a P/CF of{" "}
                    {val ? <Val>{fmtNum(val.priceToCashFlow)}</Val> : <Missing />}.
                  </p>
                  <p className="mt-2">
                    <strong>Growth &amp; ROE:</strong> {ticker}&apos;s historical earnings growth
                    rate is{" "}
                    {val?.historicalGrowthRate != null &&
                    Math.abs(val.historicalGrowthRate) > 0.5
                      ? "highly volatile "
                      : ""}
                    at {val ? <Val>{fmtPct(val.historicalGrowthRate)}</Val> : <Missing />}, with an
                    ROE of {val ? <Val>{fmtPct(val.roe)}</Val> : <Missing />} and a calculated SGR
                    of {val ? <Val>{fmtPct(val.sustainableGrowthRate)}</Val> : <Missing />}. This
                    reflects the firm&apos;s aggressive reinvestment of capital back into operations
                    to fuel future expansion rather than distributing cash to shareholders.
                  </p>
                </>
              )}
            </div>
          );
        })}

        {/* ---- 4.2 ---- */}
        <h3 className="text-base font-semibold text-slate-900 mt-4">Earnings &amp; Cash Flow Analysis</h3>
        <p>
          To gauge the underlying financial health and operational efficiency of our holdings, we
          analyzed fundamental metrics over our sample period.
        </p>

        <p className="mt-3">
          <strong>Profitability Ratios:</strong>
        </p>
        <p className="mt-1">
          <strong>Gross &amp; Operating Margins:</strong>{" "}
          {stats.map(({ ticker, val }, i) => (
            <span key={ticker}>
              {i > 0 ? (i === stats.length - 1 ? " Conversely, " : "; ") : ""}
              <strong>{ticker}</strong> maintained gross margins of{" "}
              {val ? <Val>{fmtPct(val.grossMargin)}</Val> : <Missing />} and operating margins of{" "}
              {val ? <Val>{fmtPct(val.operatingMargin)}</Val> : <Missing />}
              {i === stats.length - 1 ? "." : ""}
            </span>
          ))}
        </p>
        <p className="mt-2">
          <strong>Return on Assets (ROA) &amp; ROE:</strong>{" "}
          {stats.map(({ ticker, val }, i) => (
            <span key={ticker}>
              {i > 0 ? " " : ""}
              <strong>{ticker}</strong> reported an ROA of{" "}
              {val ? <Val>{fmtPct(val.roa)}</Val> : <Missing />} and an ROE of{" "}
              {val ? <Val>{fmtPct(val.roe)}</Val> : <Missing />}.
            </span>
          ))}
        </p>

        <p className="mt-3">
          <strong>Standard Per-Share Values:</strong>
        </p>
        <ul className="mt-1 list-disc list-inside space-y-1">
          {stats.map(({ ticker, val }) => (
            <li key={ticker}>
              <strong>{ticker}:</strong> Book Value per Share (BVPS) is{" "}
              {val ? <Val>{fmtUsd(val.bookValuePerShare)}</Val> : <Missing />}, Earnings per Share
              (EPS) is {val ? <Val>{fmtUsd(val.earningsPerShare)}</Val> : <Missing />}, and Cash
              Flow per Share (CFPS) is{" "}
              {val ? <Val>{fmtUsd(val.cashFlowPerShare)}</Val> : <Missing />}.
            </li>
          ))}
        </ul>

        <p className="mt-3">
          <strong>Standard Price Ratios:</strong>
        </p>
        <p className="mt-1">
          The market prices these distinct operational realities differently:
        </p>
        <ul className="mt-1 list-disc list-inside space-y-1">
          {stats.map(({ ticker, val, growth }) => {
            const profile = growth ? '"Growth"' : '"Value"';
            return (
              <li key={ticker}>
                <strong>{ticker}:</strong> Trades at a P/B of{" "}
                {val ? <Val>{fmtNum(val.priceToBook)}</Val> : <Missing />}, a P/E of{" "}
                {val ? <Val>{fmtNum(val.priceToEarnings)}</Val> : <Missing />}, and a P/CF of{" "}
                {val ? <Val>{fmtNum(val.priceToCashFlow)}</Val> : <Missing />}, reflecting a{" "}
                {val ? <Val>{profile}</Val> : <Placeholder label="Value / Growth" />} profile.
              </li>
            );
          })}
        </ul>

        {/* ================================================================
            SECTION 5
        ================================================================ */}
        <div className="mt-8 pt-6 border-t border-slate-100" />

        <SectionHeader num="5" title="Technical Analysis and Market Efficiency" />

        {/* ---- 5.1 ---- */}
        <h3 className="text-base font-semibold text-slate-900 mt-4">Stock Price Behavior and Relative Strength</h3>
        <p>
          To supplement our fundamental analysis, we examined the momentum and broader price
          behavior of our assets. As illustrated in the Relative Strength Chart above, we plotted
          the daily price ratios of each portfolio holding against the S&amp;P 500 (SPY) benchmark.
        </p>

        {stats.map(({ ticker, rs, val }) => (
          <div key={ticker} className="mt-3 pl-4 border-l-2 border-slate-100">
            <p>
              <strong>{ticker}&apos;s Relative Strength:</strong>{" "}
              {rs === null ? (
                <span>
                  {ticker}&apos;s relative strength data is being computed from the price history
                  loaded above.
                </span>
              ) : rs.volatilityProfile === "low" ? (
                <>
                  {ticker}&apos;s line remains <Val>relatively flat to slightly undulating</Val>{" "}
                  (coefficient of variation: {(rs.cv * 100).toFixed(1)}%), confirming its{" "}
                  {val?.calculatedBeta != null ? (
                    <>
                      low-beta (<Val>β = {fmtNum(val.calculatedBeta)}</Val>)
                    </>
                  ) : (
                    "defensive"
                  )}{" "}
                  nature. It generally tracks the broader market with less volatile swings, acting
                  as a stabilizing anchor in our portfolio.
                </>
              ) : rs.volatilityProfile === "moderate" ? (
                <>
                  {ticker}&apos;s relative strength line exhibits{" "}
                  <Val>moderate fluctuations</Val> (CV:{" "}
                  {(rs.cv * 100).toFixed(1)}%), with a{" "}
                  {rs.trend === "outperforming" ? "generally upward" : "generally downward"} bias
                  relative to the S&amp;P 500 over the sample period.
                </>
              ) : (
                <>
                  In stark contrast, {ticker}&apos;s relative strength line exhibits{" "}
                  <Val>massive peaks and troughs</Val> (CV: {(rs.cv * 100).toFixed(1)}%). During
                  periods of favorable sector momentum, {ticker} drastically outperformed the
                  S&amp;P 500, visible as sharp upward spikes. However, it also suffered severe
                  drawdowns, underperforming the broader market during cyclical downturns.
                </>
              )}
            </p>
          </div>
        ))}

        {/* ---- 5.2 ---- */}
        <h3 className="text-base font-semibold text-slate-900 mt-4">Moving Averages and Trend Identification</h3>
        <p>
          Moving averages help smooth out daily price noise to reveal underlying directional trends.
          As seen in the Moving Average Chart above, we plotted the raw daily closing prices
          alongside a <Val>{windowSize}-day</Val> Simple Moving Average (SMA).
        </p>

        {stats.map(({ ticker, ma }) => (
          <div key={ticker} className="mt-3 pl-4 border-l-2 border-slate-100">
            <p>
              <strong>{ticker}:</strong>{" "}
              {ma.hugsMA ? (
                <>
                  {ticker}&apos;s price action <Val>hugs its moving average closely</Val>. We
                  observed <Val>{ma.totalCrossovers}</Val> total crossover signal
                  {ma.totalCrossovers !== 1 ? "s" : ""} over the period, pointing to a long-term,
                  slow-moving consolidation trend.
                </>
              ) : (
                <>
                  {ticker}&apos;s raw price{" "}
                  <Val>frequently breaks aggressively above and below its moving average</Val>. We
                  observed <Val>{ma.totalCrossovers}</Val> crossover signal
                  {ma.totalCrossovers !== 1 ? "s" : ""} in total (
                  {ma.bullishCount} bullish, {ma.bearishCount} bearish).{" "}
                  {ma.firstBullish && (
                    <>
                      A notable bullish crossover occurred around{" "}
                      <Val>{fmtDate(ma.firstBullish)}</Val>
                      {ma.firstBearish ? (
                        <>
                          , followed by a bearish crossover around{" "}
                          <Val>{fmtDate(ma.firstBearish)}</Val>
                        </>
                      ) : null}
                      . These frequent intersections highlight {ticker}&apos;s highly reactive price
                      behavior.
                    </>
                  )}
                </>
              )}
            </p>
          </div>
        ))}

        {/* ---- 5.3 ---- */}
        <h3 className="text-base font-semibold text-slate-900 mt-4">Market Efficiency Implications</h3>
        <p>
          The technical patterns observed prompt an evaluation of the{" "}
          <Val>Efficient Market Hypothesis (EMH)</Val>. If the market operates under{" "}
          <strong>Weak-Form Efficiency</strong>, all historical price and volume data should already
          be fully reflected in current stock prices, making it impossible to consistently generate
          abnormal returns (Jensen&apos;s Alpha) using moving averages and relative strength signals
          alone.
        </p>
        <p className="mt-2">
          While our technical analysis clearly visualizes past momentum and volatility—particularly
          for{" "}
          {stats
            .filter((s) => s.rs?.volatilityProfile === "high")
            .map((s) => s.ticker)
            .join(" and ") || "high-beta holdings"}
          —it serves more as a rear-view <strong>risk management tool</strong> rather than a
          guaranteed predictive crystal ball. The rapid price corrections observed following
          earnings surprises suggest a market that quickly digests new public information (
          <strong>Semi-Strong Form Efficiency</strong>), forcing prices to their new equilibrium
          almost instantly.
        </p>
        <p className="mt-2">
          Beta-weighted allocations across{" "}
          {stats.filter((s) => s.rs?.volatilityProfile === "low").map((s) => s.ticker).join(", ") ||
            "lower-volatility holdings"}{" "}
          (defensive anchor) and{" "}
          {stats.filter((s) => s.rs?.volatilityProfile === "high").map((s) => s.ticker).join(", ") ||
            "higher-volatility growth names"}{" "}
          (return engine) form the core of our <Val>barbell strategy</Val>, balancing downside
          protection with upside participation.
        </p>
      </div>
    </div>
  );
}
