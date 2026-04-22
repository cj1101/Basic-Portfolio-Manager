import {
  Activity,
  ArrowRight,
  Gauge,
  Rocket,
  Scale,
  TrendingUp,
} from "lucide-react";
import { usePortfolio } from "@/state/portfolioContext";
import { KpiCard } from "../kpi/KpiCard";
import { decimals, pct, shortDate, signedPct } from "@/lib/format";
import { Tooltip } from "@/components/ui/Tooltip";
import { metricTooltip } from "@/lib/metricTooltips";

const STEPS = [
  {
    title: "Build the universe",
    description:
      "Fetch 5-year daily history for every ticker, then estimate expected returns, volatilities, and the full covariance matrix.",
  },
  {
    title: "Find the tangency portfolio",
    description:
      "Solve the constrained Sharpe-maximization problem to locate the Optimal Risky Portfolio on the efficient frontier.",
  },
  {
    title: "Allocate along the CAL",
    description:
      "Combine the ORP with the risk-free asset using your risk aversion to pick the mean-variance optimal complete portfolio.",
  },
];

export function OverviewTab() {
  const { result, riskProfile } = usePortfolio();
  const { orp, complete, market, riskFreeRate } = result;
  const topStock = result.stocks.reduce((best, s) =>
    s.alpha > best.alpha ? s : best,
  );

  return (
    <div className="flex flex-col gap-8">
      <section>
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold text-slate-900">Your complete portfolio</h3>
            <p className="mt-1 text-sm text-slate-500">
              Snapshot as of {shortDate(result.asOf)} · driven by your current risk aversion of{" "}
              <strong>A = {riskProfile.riskAversion}</strong>.
            </p>
          </div>
        </header>
        <div className="grid gap-4 md:grid-cols-4">
          <KpiCard
            label="Expected return"
            value={pct(complete.expectedReturn, 2)}
            sublabel={`vs. target ${riskProfile.targetReturn != null ? pct(riskProfile.targetReturn, 1) : "—"}`}
            labelTooltip={metricTooltip("completeExpectedReturn", {
              value: complete.expectedReturn,
              riskFreeRate,
              orpExpectedReturn: orp.expectedReturn,
            })}
            icon={<TrendingUp size={16} />}
            tone="brand"
          />
          <KpiCard
            label="Volatility (σ)"
            value={pct(complete.stdDev, 2)}
            sublabel={`ORP σ = ${pct(orp.stdDev, 2)}`}
            labelTooltip={metricTooltip("completeStdDev", {
              value: complete.stdDev,
              orpStdDev: orp.stdDev,
            })}
            icon={<Activity size={16} />}
          />
          <KpiCard
            label="Weight in ORP"
            value={pct(complete.yStar, 1)}
            sublabel={complete.leverageUsed ? "Leverage engaged (y* > 100%)" : "No leverage"}
            labelTooltip={metricTooltip("yStar", {
              value: complete.yStar,
              riskFreeRate,
              orpExpectedReturn: orp.expectedReturn,
              orpStdDev: orp.stdDev,
            })}
            icon={<Scale size={16} />}
            tone={complete.leverageUsed ? "negative" : "neutral"}
          />
          <KpiCard
            label="ORP Sharpe ratio"
            value={decimals(orp.sharpe, 3)}
            sublabel={`r_f = ${pct(riskFreeRate, 2)}`}
            labelTooltip={metricTooltip("orpSharpe", { value: orp.sharpe, riskFreeRate })}
            icon={<Gauge size={16} />}
          />
        </div>
      </section>

      <section>
        <h3 className="mb-3 text-xl font-semibold text-slate-900">How we got here</h3>
        <div className="grid gap-4 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <article
              key={s.title}
              className="card flex flex-col gap-2 p-5 transition-shadow hover:shadow-md"
            >
              <div className="flex items-center gap-2">
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
                  {i + 1}
                </span>
                <h4 className="text-base font-semibold text-slate-900">{s.title}</h4>
              </div>
              <p className="text-sm leading-relaxed text-slate-600">{s.description}</p>
              {i < STEPS.length - 1 ? (
                <ArrowRight
                  size={18}
                  className="hidden text-slate-300 md:block md:self-end"
                  aria-hidden
                />
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section className="card p-5">
        <div className="flex items-start gap-3">
          <Rocket className="text-brand-600" size={22} aria-hidden />
          <div>
            <h3 className="text-lg font-semibold text-slate-900">Today's headline</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              <strong>{topStock.ticker}</strong> is the top alpha contributor with{" "}
              <Tooltip label={metricTooltip("alpha", { value: topStock.alpha })}>
                <span className="cursor-help underline decoration-dotted underline-offset-2">α</span>
              </Tooltip>{" "}
              ={" "}
              <span className="font-semibold text-emerald-600">{signedPct(topStock.alpha)}</span>{" "}
              and{" "}
              <Tooltip label={metricTooltip("beta", { value: topStock.beta })}>
                <span className="cursor-help underline decoration-dotted underline-offset-2">β</span>
              </Tooltip>{" "}
              = {decimals(topStock.beta, 2)}. At your current risk aversion the model
              allocates <strong>{pct(complete.yStar * (orp.weights[topStock.ticker] ?? 0), 2)}</strong> of
              the portfolio to it. The market benchmark is expected to return{" "}
              {pct(market.expectedReturn, 2)} with{" "}
              <Tooltip label={metricTooltip("stdDev", { value: market.stdDev })}>
                <span className="cursor-help underline decoration-dotted underline-offset-2">σ</span>
              </Tooltip>{" "}
              = {pct(market.stdDev, 2)}.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
