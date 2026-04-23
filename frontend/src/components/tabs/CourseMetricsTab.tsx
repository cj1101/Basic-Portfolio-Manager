import { useCallback, useState } from "react";
import { Loader2 } from "lucide-react";
import { usePortfolio } from "@/state/portfolioContext";
import { postAnalyticsPerformance, postValuation, ApiError } from "@/lib/api";
import type {
  AnalyticsPerformanceResult,
  ValuationResult,
} from "@/types/contracts";

/** Valuation may need several POSTs when AV throttles; each attempt can take a while (many fundamentals calls). */
const VALUATION_MAX_ATTEMPTS = 45;
const VALUATION_RETRY_DELAY_MS = 1000;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isValuationThrottleError(e: unknown): boolean {
  if (!(e instanceof ApiError)) return false;
  if (e.status === 429 || e.status === 503) return true;
  if (e.code === "DATA_PROVIDER_UNAVAILABLE" || e.code === "DATA_PROVIDER_RATE_LIMIT") {
    return true;
  }
  const m = e.message.toLowerCase();
  return (
    m.includes("alpha vantage") ||
    m.includes("alphavantage") ||
    m.includes("rate limit") ||
    m.includes("sparingly") ||
    m.includes("try again shortly")
  );
}

function fmtPct(x: number | null | undefined, digits = 4): string {
  if (x === null || x === undefined || Number.isNaN(x)) {
    return "—";
  }
  return `${(x * 100).toFixed(digits)}%`;
}

export function CourseMetricsTab() {
  const { tickers, returnFrequency, lookbackYears, result } = usePortfolio();
  const [analytics, setAnalytics] = useState<AnalyticsPerformanceResult | null>(null);
  const [valuation, setValuation] = useState<ValuationResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingVal, setLoadingVal] = useState(false);
  const [valuationThrottleAttempt, setValuationThrottleAttempt] = useState(0);

  const loadAnalytics = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const orpWeights = { ...result.orp.weights };
      for (const t of tickers) {
        if (!(t in orpWeights)) {
          orpWeights[t] = 0;
        }
      }
      const res = await postAnalyticsPerformance({
        tickers,
        orpWeights,
        returnFrequency,
        lookbackYears,
        yStar: result.complete.yStar,
        weightRiskFree: result.complete.weightRiskFree,
      });
      setAnalytics(res);
    } catch (e) {
      setAnalytics(null);
      setErr(e instanceof ApiError ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  }, [tickers, returnFrequency, lookbackYears, result]);

  const loadValuation = useCallback(async () => {
    setErr(null);
    setLoadingVal(true);
    setValuationThrottleAttempt(0);
    const body = {
      tickers,
      ddmGordonG: 0.03,
      ddmTwoStage: { g1: 0.08, g2: 0.03, nPeriods: 5 },
      wacc: 0.09,
      fcffGrowth: 0.02,
      fcffTerminalGrowth: 0.02,
    };
    try {
      for (let attempt = 1; attempt <= VALUATION_MAX_ATTEMPTS; attempt += 1) {
        setValuationThrottleAttempt(attempt);
        try {
          const res = await postValuation(body);
          setValuation(res);
          return;
        } catch (e) {
          if (!isValuationThrottleError(e) || attempt >= VALUATION_MAX_ATTEMPTS) {
            setValuation(null);
            setErr(
              e instanceof ApiError
                ? e.message
                : "Valuation failed (fundamentals unavailable from Yahoo or Alpha Vantage)",
            );
            return;
          }
          // Fixed pacing: server may send Retry-After up to 60s for 429; long silent waits looked "stuck".
          await delay(VALUATION_RETRY_DELAY_MS);
        }
      }
    } finally {
      setLoadingVal(false);
      setValuationThrottleAttempt(0);
    }
  }, [tickers]);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Course metrics &amp; Fama–French 3</h2>
        <p className="mt-1 text-sm text-slate-600">
          Uses the <strong>current ORP weights</strong> from the optimization above. Treynor, Jensen, SIM
          variance split, 3/5/10-year mean monthly returns, and three-factor betas are computed on the
          server.
        </p>
        <button
          type="button"
          onClick={loadAnalytics}
          disabled={loading}
          className="mt-3 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Loading…" : "Load analytics"}
        </button>
      </div>

      {err ? (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {err}
        </p>
      ) : null}

      {analytics ? (
        <div className="space-y-4 text-sm">
          <section>
            <h3 className="font-medium text-slate-800">ORP — Treynor &amp; Jensen</h3>
            <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">Treynor</dt>
                <dd>{fmtPct(analytics.orp.treynor, 2)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Jensen &alpha; (annualized)</dt>
                <dd>{fmtPct(analytics.orp.jensenAlpha, 2)}</dd>
              </div>
            </dl>
          </section>
          <section>
            <h3 className="font-medium text-slate-800">SIM variance (ORP)</h3>
            <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div>
                <dt className="text-slate-500">Total &sigma;&sup2;</dt>
                <dd>{analytics.orp.totalVariance.toFixed(6)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Systematic</dt>
                <dd>{analytics.orp.systematicVariance.toFixed(6)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Unsystematic</dt>
                <dd>{analytics.orp.unsystematicVariance.toFixed(6)}</dd>
              </div>
            </dl>
          </section>
          {analytics.complete ? (
            <section>
              <h3 className="font-medium text-slate-800">Complete portfolio (approximate)</h3>
              <dl className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                <div>
                  <dt className="text-slate-500">Treynor</dt>
                  <dd>{fmtPct(analytics.complete.treynor, 2)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Jensen &alpha; (y &times; ORP &alpha;)</dt>
                  <dd>{fmtPct(analytics.complete.jensenAlpha, 2)}</dd>
                </div>
              </dl>
            </section>
          ) : null}
          {analytics.holding.length > 0 ? (
            <section>
              <h3 className="font-medium text-slate-800">Holding period — mean monthly (simple) returns</h3>
              <table className="mt-2 w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="py-1 pr-4">Years</th>
                    <th className="py-1 pr-4">Arithmetic</th>
                    <th className="py-1">Geometric</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.holding.map((h) => (
                    <tr key={h.years} className="border-b border-slate-100">
                      <td className="py-1 pr-4">{h.years}</td>
                      <td className="py-1 pr-4">{fmtPct(h.arithmeticMeanMonthlyReturn)} / mo</td>
                      <td className="py-1">{fmtPct(h.geometricMeanMonthlyReturn)} / mo</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ) : null}
          {analytics.famaFrench.length > 0 ? (
            <section>
              <h3 className="font-medium text-slate-800">Fama–French 3 (per ticker)</h3>
              <div className="mt-2 space-y-3">
                {analytics.famaFrench.map((f) => (
                  <div key={f.ticker} className="rounded border border-slate-200 bg-white p-3">
                    <p className="font-mono text-sm font-medium">{f.ticker}</p>
                    <p className="text-xs text-slate-600">
                      E(r) FF3: {fmtPct(f.expectedReturnFf3, 2)} &middot; E(r) CAPM (monthly OLS):{" "}
                      {fmtPct(f.expectedReturnCapm, 2)} &middot; &beta;<sub>SMB</sub> {f.betaSmb.toFixed(3)}{" "}
                      &middot; &beta;<sub>HML</sub> {f.betaHml.toFixed(3)}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      ) : null}

      <div>
        <h2 className="text-lg font-semibold text-slate-900">Valuation (FCFF, FCFE, DDM)</h2>
        <p className="mt-1 text-sm text-slate-600">
          Requires <code>ALPHA_VANTAGE_API_KEY</code> and statement endpoints. Defaults: WACC 9%, FCFF
          growth 2%, Gordon g 3%, two-stage DDM (g1 8%, g2 3%, 5 years).
        </p>
        <button
          type="button"
          onClick={loadValuation}
          disabled={loadingVal}
          className="mt-3 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 disabled:opacity-50"
        >
          {loadingVal ? "Loading…" : "Load valuation"}
        </button>
        {loadingVal ? (
          <div
            className="mt-4 flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 shadow-sm"
            role="status"
            aria-live="polite"
          >
            <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-brand-600" aria-hidden />
            <div>
              <p className="font-medium text-slate-900">
                {valuationThrottleAttempt > 1
                  ? "Alpha Vantage throttled — retrying"
                  : "Loading valuation"}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Attempt {Math.max(1, valuationThrottleAttempt)} of {VALUATION_MAX_ATTEMPTS}. Each run fetches
                several fundamentals per ticker and can take a while.
                {valuationThrottleAttempt > 1 ? (
                  <>
                    {" "}
                    Waiting <strong>{VALUATION_RETRY_DELAY_MS / 1000}s</strong> before the next request.
                  </>
                ) : null}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      {valuation ? (
        <div className="space-y-3 text-sm">
          {valuation.perTicker.map((v) => (
            <div key={v.ticker} className="rounded border border-slate-200 bg-white p-3">
              <p className="font-mono font-medium">{v.ticker}</p>
              <p className="text-slate-600">
                FCFF (last year $): {v.fcff?.toFixed(0) ?? "—"} &middot; FCFE (last year $):{" "}
                {v.fcfe?.toFixed(0) ?? "—"} &middot; k<sub>e</sub>: {fmtPct(v.costOfEquity, 2)}
              </p>
              <p className="text-slate-600">
                FCFF DCF $/sh: {v.fcffValuePerShare?.toFixed(2) ?? "—"} &middot; FCFE DCF $/sh:{" "}
                {v.fcfeValuePerShare?.toFixed(2) ?? "—"}
              </p>
              <p className="text-slate-600">
                DDM Gordon: {v.ddmGordon?.toFixed(2) ?? "—"} &middot; two-stage:{" "}
                {v.ddmTwoStage?.toFixed(2) ?? "—"}
              </p>
              {v.warnings.length > 0 ? (
                <ul className="mt-1 list-inside list-disc text-xs text-amber-800">
                  {v.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
