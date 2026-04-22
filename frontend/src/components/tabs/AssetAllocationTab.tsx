import { AlertCircle, HelpCircle, PieChart, Sliders } from "lucide-react";
import clsx from "clsx";
import { usePortfolio } from "@/state/portfolioContext";
import { CALChart } from "../charts/CALChart";
import { CorrelationHeatmap } from "../charts/CorrelationHeatmap";
import { WeightsBarChart } from "../charts/WeightsBarChart";
import { KpiCard } from "../kpi/KpiCard";
import { decimals, pct } from "@/lib/format";
import { Tooltip } from "@/components/ui/Tooltip";
import { metricTooltip } from "@/lib/metricTooltips";

export function AssetAllocationTab() {
  const { result, riskProfile } = usePortfolio();
  const { orp, complete, riskFreeRate, correlation } = result;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <div className="flex items-center gap-2 text-slate-900">
          <PieChart size={20} className="text-brand-600" aria-hidden />
          <h3 className="text-xl font-semibold">Step 3 — Your Asset Allocation</h3>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-slate-600">
          Once we know the ORP and the risk-free rate, choosing a complete portfolio reduces to a
          single number:{" "}
          <Tooltip label={metricTooltip("yStar", { value: complete.yStar })}>
            <strong className="cursor-help underline decoration-dotted underline-offset-2">y*</strong>
          </Tooltip>
          , the fraction of your wealth in the ORP. It is set by
          maximizing the mean-variance utility{" "}
          <code className="font-mono text-xs">U = E(r_C) − ½ · A · σ_C²</code>.
        </p>
      </header>

      <section className="card p-5">
        <CALChart orp={orp} riskFreeRate={riskFreeRate} complete={complete} />
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        <KpiCard
          label="Weight in ORP (y*)"
          value={pct(complete.yStar, 2)}
          sublabel={`Risk-aversion A = ${riskProfile.riskAversion}`}
          labelTooltip={metricTooltip("yStar", {
            value: complete.yStar,
            riskFreeRate,
            orpExpectedReturn: orp.expectedReturn,
            orpStdDev: orp.stdDev,
          })}
          icon={<Sliders size={16} />}
          tone={complete.leverageUsed ? "negative" : "brand"}
        />
        <KpiCard
          label="Weight in risk-free"
          value={pct(complete.weightRiskFree, 2)}
          sublabel={`r_f = ${pct(riskFreeRate, 2)}`}
          labelTooltip={metricTooltip("weightRiskFree", { value: complete.weightRiskFree })}
        />
        <KpiCard
          label="Complete E(r)"
          value={pct(complete.expectedReturn, 2)}
          sublabel={`ORP excess · y* = ${decimals((orp.expectedReturn - riskFreeRate) * complete.yStar, 4)}`}
          labelTooltip={metricTooltip("completeExpectedReturn", {
            value: complete.expectedReturn,
            riskFreeRate,
            orpExpectedReturn: orp.expectedReturn,
          })}
        />
        <KpiCard
          label="Complete σ"
          value={pct(complete.stdDev, 2)}
          sublabel={`|y*| · σ_ORP = ${pct(Math.abs(complete.yStar) * orp.stdDev, 2)}`}
          labelTooltip={metricTooltip("completeStdDev", {
            value: complete.stdDev,
            orpStdDev: orp.stdDev,
          })}
        />
      </section>

      {complete.leverageUsed ? (
        <div
          role="alert"
          className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4"
        >
          <AlertCircle className="mt-0.5 shrink-0 text-amber-600" size={18} aria-hidden />
          <p className="text-sm leading-relaxed text-amber-900">
            <strong>Leverage is in use.</strong> Reaching your target return requires borrowing at
            r_f and investing <strong>{pct(complete.yStar, 1)}</strong> of your capital in the
            ORP. The risk-free weight is negative ({pct(complete.weightRiskFree, 1)}).{" "}
            {complete.targetReturnOverride ? (
              <>
                This exceeds the utility-max y* of {decimals(complete.yUtility, 2)} — the slider's
                A is overridden by your target-return setting.
              </>
            ) : null}
          </p>
        </div>
      ) : null}

      <section className="grid gap-6 md:grid-cols-2">
        <article className="card p-5">
          <h4 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            ORP weights (fully-invested risky portion)
          </h4>
          <WeightsBarChart weights={orp.weights} />
        </article>
        <article className="card p-5">
          <h4 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Complete portfolio weights (risky + risk-free)
          </h4>
          <WeightsBarChart weights={complete.weights} riskFreeWeight={complete.weightRiskFree} />
        </article>
      </section>

      <section className="card p-5">
        <div className="mb-3 flex items-start justify-between gap-2">
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Synergies (correlation)
          </h4>
          <Tooltip label={metricTooltip("assetSynergy")}>
            <span className="inline-flex cursor-help text-slate-400" aria-label="About correlation">
              <HelpCircle size={16} />
            </span>
          </Tooltip>
        </div>
        <p className="mb-3 text-sm leading-relaxed text-slate-600">
          In quantitative finance, how different stocks move together is captured by <strong>covariance</strong> and{" "}
          <strong>correlation</strong>. The optimizer already uses the full covariance (or, equivalently, all pairwise
          covariances) to measure <em>interactive risk</em> and to find the ORP. Raw covariance is hard to read, so
          the table below shows the <strong>correlation matrix</strong> on a −1.0 to +1.0 scale: each off-diagonal entry
          is Covariance(<em>i</em>, <em>j</em>) / (σ<sub>i</sub> σ<sub>j</sub>).
        </p>
        <p className="mb-4 text-sm leading-relaxed text-slate-600">
          <strong>How to read it:</strong> this matrix is your synergy view. For a well-diversified book you generally
          want many pairs with low or negative correlation (more green) so shocks do not line up. If most pairs are
          highly positive (red), a broad market move that hurts one name is more likely to hurt them all.
        </p>
        <CorrelationHeatmap correlation={correlation} />
      </section>

      <section className="card overflow-hidden">
        <div className="border-b border-slate-100 px-4 py-2.5 text-sm font-medium text-slate-700">
          Weight breakdown
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Position
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  <Tooltip label={metricTooltip("orpWeight")}>
                    <span className="cursor-help underline decoration-dotted underline-offset-2">
                      ORP weight
                    </span>
                  </Tooltip>
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  <Tooltip label={metricTooltip("yStar", { value: complete.yStar })}>
                    <span className="cursor-help underline decoration-dotted underline-offset-2">
                      Complete weight (y* · w_ORP)
                    </span>
                  </Tooltip>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
              {Object.entries(orp.weights).map(([ticker, w]) => {
                const complete_w = complete.weights[ticker] ?? 0;
                return (
                  <tr key={ticker} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 font-semibold text-slate-900">{ticker}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{pct(w, 2)}</td>
                    <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-brand-700">
                      {pct(complete_w, 2)}
                    </td>
                  </tr>
                );
              })}
              <tr className="bg-slate-50/60">
                <td className="px-4 py-2.5 font-semibold text-slate-900">
                  <Tooltip label={metricTooltip("riskFreeRate", { riskFreeRate })}>
                    <span className="cursor-help underline decoration-dotted underline-offset-2">
                      Risk-free (r_f)
                    </span>
                  </Tooltip>
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums text-slate-400">—</td>
                <td
                  className={clsx(
                    "px-4 py-2.5 text-right font-semibold tabular-nums",
                    complete.weightRiskFree < 0 ? "text-rose-600" : "text-slate-700",
                  )}
                >
                  {pct(complete.weightRiskFree, 2)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
