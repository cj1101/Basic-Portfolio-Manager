import clsx from "clsx";
import type { StockMetrics, Ticker } from "@/types/contracts";
import { decimals, pct, signedPct, integer } from "@/lib/format";
import { Tooltip } from "@/components/ui/Tooltip";
import { metricTooltip } from "@/lib/metricTooltips";

export interface MetricsTableProps {
  stocks: StockMetrics[];
  weights?: Record<Ticker, number>;
  caption?: string;
}

const columns = [
  { key: "ticker", label: "Ticker", align: "left", tooltip: undefined },
  { key: "expectedReturn", label: "E(r)", align: "right", tooltip: metricTooltip("stockExpectedReturn") },
  { key: "stdDev", label: "σ", align: "right", tooltip: metricTooltip("stockStdDev") },
  { key: "beta", label: "β", align: "right", tooltip: metricTooltip("beta") },
  { key: "alpha", label: "α", align: "right", tooltip: metricTooltip("alpha") },
  { key: "firmSpecificVar", label: "Firm-specific var", align: "right", tooltip: metricTooltip("firmSpecificVar") },
  { key: "nObservations", label: "N obs", align: "right", tooltip: metricTooltip("nObservations") },
] as const;

export function MetricsTable({ stocks, weights, caption }: MetricsTableProps) {
  const showWeight = weights != null;
  return (
    <div className="card overflow-hidden">
      {caption ? (
        <div className="border-b border-slate-100 px-4 py-2.5 text-sm font-medium text-slate-700">
          {caption}
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  className={clsx("px-4 py-2 font-medium", c.align === "right" && "text-right")}
                >
                  {c.tooltip ? (
                    <Tooltip label={c.tooltip}>
                      <span className="cursor-help underline decoration-dotted underline-offset-2">
                        {c.label}
                      </span>
                    </Tooltip>
                  ) : (
                    c.label
                  )}
                </th>
              ))}
              {showWeight ? (
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  <Tooltip label={metricTooltip("orpWeight")}>
                    <span className="cursor-help underline decoration-dotted underline-offset-2">
                      ORP weight
                    </span>
                  </Tooltip>
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
            {stocks.map((s) => {
              const w = weights?.[s.ticker];
              return (
                <tr key={s.ticker} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-semibold text-slate-900">{s.ticker}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{pct(s.expectedReturn)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{pct(s.stdDev)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{decimals(s.beta, 2)}</td>
                  <td
                    className={clsx(
                      "px-4 py-2.5 text-right tabular-nums",
                      s.alpha > 0 && "text-emerald-600",
                      s.alpha < 0 && "text-rose-600",
                    )}
                  >
                    {signedPct(s.alpha)}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{decimals(s.firmSpecificVar, 3)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{integer(s.nObservations)}</td>
                  {showWeight ? (
                    <td className="px-4 py-2.5 text-right font-semibold tabular-nums text-brand-700">
                      {w != null ? pct(w, 2) : "—"}
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
