import { AlertTriangle, Database, ExternalLink, Info } from "lucide-react";
import clsx from "clsx";
import { usePortfolio } from "@/state/portfolioContext";

interface DataSource {
  name: string;
  purpose: string;
  cadence: string;
  rateLimit: string;
  fallback: string;
  status: "connected" | "planned";
  url?: string;
}

const DATA_SOURCES: DataSource[] = [
  {
    name: "Alpha Vantage",
    purpose: "Daily OHLCV for individual tickers (5-year lookback).",
    cadence: "On demand, 24h SQLite cache",
    rateLimit: "5 req / min · 500 / day (free tier)",
    fallback: "Falls back to Yahoo Finance when rate-limited; surfaces DATA_PROVIDER_RATE_LIMIT otherwise.",
    status: "connected",
    url: "https://www.alphavantage.co/",
  },
  {
    name: "Yahoo Finance",
    purpose: "Secondary OHLCV provider used when Alpha Vantage is rate-limited or unavailable.",
    cadence: "On demand, shared SQLite cache",
    rateLimit: "Soft-capped (scraper)",
    fallback: "Opt-in deterministic mock series when USE_MOCK_FALLBACK=true.",
    status: "connected",
  },
  {
    name: "FRED (St. Louis Fed)",
    purpose: "3-month T-Bill series for the risk-free rate (DGS3MO).",
    cadence: "Once per 24h",
    rateLimit: "120 req / min (generous)",
    fallback: "Hardcoded snapshot (source=FALLBACK) when FRED is unreachable.",
    status: "connected",
    url: "https://fred.stlouisfed.org/",
  },
  {
    name: "SPY proxy",
    purpose: "Market benchmark for CAPM beta/alpha regressions.",
    cadence: "Piggybacks on Alpha Vantage daily close",
    rateLimit: "Shared with AV",
    fallback: "Latest cached SPY history.",
    status: "connected",
  },
  {
    name: "Questionnaire scoring",
    purpose: "Maps 6 multiple-choice answers to A ∈ [1, 10].",
    cadence: "Runs entirely client-side",
    rateLimit: "—",
    fallback: "N/A — deterministic.",
    status: "connected",
  },
  {
    name: "SQLite cache (local)",
    purpose: "Stores price bars, quotes, questionnaire results, and saved portfolios.",
    cadence: "Writes on every successful provider response",
    rateLimit: "—",
    fallback: "Creates fresh tables on first run.",
    status: "connected",
  },
];

export function ApisDataTab() {
  const { result, isFallbackResult, lastUpdatedAt } = usePortfolio();
  const warnings = result.warnings ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <div className="flex items-center gap-2 text-slate-900">
          <Database size={20} className="text-brand-600" aria-hidden />
          <h3 className="text-xl font-semibold">APIs and Data Sources</h3>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-slate-600">
          Every number in this report ultimately traces back to one of the providers below. Each
          source has a rate limit, a cache strategy, and a typed fallback so the UI remains
          responsive even when upstream APIs degrade.
        </p>
      </header>

      {warnings.length > 0 ? (
        <aside
          role="status"
          className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4"
        >
          <AlertTriangle className="mt-0.5 shrink-0 text-amber-600" size={18} aria-hidden />
          <div className="flex-1 text-sm">
            <p className="font-semibold text-amber-900">Data warnings</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-amber-800">
              {warnings.map((w, i) => (
                <li key={`${i}-${w}`}>{w}</li>
              ))}
            </ul>
          </div>
        </aside>
      ) : null}

      {isFallbackResult ? (
        <aside
          role="status"
          className="flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4"
        >
          <Info className="mt-0.5 shrink-0 text-slate-500" size={18} aria-hidden />
          <div className="flex-1 text-sm">
            <p className="font-semibold text-slate-700">Showing offline sample data</p>
            <p className="text-slate-600">
              The backend hasn't responded yet — charts are rendering the FIXTURES.md sample until
              the first <code className="font-mono text-xs">/api/optimize</code> call succeeds.
            </p>
          </div>
        </aside>
      ) : (
        <p className="text-xs text-slate-500">
          Last optimized:{" "}
          {lastUpdatedAt
            ? new Date(lastUpdatedAt).toLocaleString()
            : "—"}
        </p>
      )}

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Source
                </th>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Purpose
                </th>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Refresh cadence
                </th>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Rate limit
                </th>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Fallback
                </th>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
              {DATA_SOURCES.map((src) => (
                <tr key={src.name} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-semibold text-slate-900">
                    {src.url ? (
                      <a
                        href={src.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex items-center gap-1 text-brand-700 hover:underline"
                      >
                        {src.name}
                        <ExternalLink size={12} aria-hidden />
                      </a>
                    ) : (
                      src.name
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{src.purpose}</td>
                  <td className="px-4 py-3 text-slate-600">{src.cadence}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-600">{src.rateLimit}</td>
                  <td className="px-4 py-3 text-slate-600">{src.fallback}</td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                        src.status === "connected"
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-amber-50 text-amber-700",
                      )}
                    >
                      {src.status === "connected" ? "Connected" : "Planned"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <section className="grid gap-4 md:grid-cols-2">
        <article className="card p-5">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Numerical conventions
          </h4>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-slate-600">
            <li>All returns/variances are annualized decimals — never intermediate-rounded.</li>
            <li>Covariance matrices are forced symmetric and positive semi-definite.</li>
            <li>Dates use the NYSE calendar; weekends and holidays are dropped before stats.</li>
          </ul>
        </article>
        <article className="card p-5">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Typed error taxonomy
          </h4>
          <ul className="mt-2 space-y-1.5 text-sm text-slate-600">
            {[
              "UNKNOWN_TICKER",
              "INSUFFICIENT_HISTORY",
              "DATA_PROVIDER_RATE_LIMIT",
              "OPTIMIZER_INFEASIBLE",
              "OPTIMIZER_NON_PSD_COVARIANCE",
            ].map((code) => (
              <li key={code}>
                <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs">{code}</code>
              </li>
            ))}
          </ul>
        </article>
      </section>
    </div>
  );
}
