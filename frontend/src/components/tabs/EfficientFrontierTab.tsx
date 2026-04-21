import { Compass, TrendingUp } from "lucide-react";
import { usePortfolio } from "@/state/portfolioContext";
import { EfficientFrontierChart } from "../charts/EfficientFrontierChart";
import { MetricsTable } from "../kpi/MetricsTable";
import { decimals, pct } from "@/lib/format";

export function EfficientFrontierTab() {
  const { result } = usePortfolio();
  const { frontierPoints, orp, stocks } = result;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <div className="flex items-center gap-2 text-slate-900">
          <Compass size={20} className="text-brand-600" aria-hidden />
          <h3 className="text-xl font-semibold">Step 1 — The Efficient Frontier</h3>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-slate-600">
          Every dot on the blue line is a portfolio that offers the maximum possible expected
          return for its level of volatility. The red marker is the <strong>Optimal Risky
          Portfolio</strong> (ORP) — the specific point on the frontier that maximizes the Sharpe
          ratio.
        </p>
      </header>

      <section className="card p-5">
        <EfficientFrontierChart frontier={frontierPoints} orp={orp} stocks={stocks} />
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <article className="card p-5">
          <span className="stat-label">ORP Expected Return</span>
          <p className="stat-value text-brand-700">{pct(orp.expectedReturn, 2)}</p>
          <p className="text-xs text-slate-500">E(r_ORP) = Σ w_i · E(r_i)</p>
        </article>
        <article className="card p-5">
          <span className="stat-label">ORP Volatility</span>
          <p className="stat-value">{pct(orp.stdDev, 2)}</p>
          <p className="text-xs text-slate-500">σ_ORP = sqrt(wᵀ Σ w)</p>
        </article>
        <article className="card p-5 border-brand-200 bg-brand-50/40">
          <span className="stat-label">ORP Sharpe</span>
          <p className="stat-value text-brand-700">
            {decimals(orp.sharpe, 3)}
            <TrendingUp className="ml-1 inline align-middle text-emerald-500" size={20} />
          </p>
          <p className="text-xs text-slate-500">(E(r_ORP) − r_f) / σ_ORP</p>
        </article>
      </section>

      <section>
        <h4 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Stocks driving the frontier
        </h4>
        <MetricsTable stocks={stocks} weights={orp.weights} caption="Per-stock contributions to the ORP" />
      </section>
    </div>
  );
}
