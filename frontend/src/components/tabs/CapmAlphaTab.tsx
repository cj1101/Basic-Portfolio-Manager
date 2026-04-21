import { LineChart as LineChartIcon, Sparkles } from "lucide-react";
import clsx from "clsx";
import { usePortfolio } from "@/state/portfolioContext";
import { SMLChart } from "../charts/SMLChart";
import { capmRequiredReturn, stocksForSML } from "@/lib/sml";
import { decimals, pct, signedPct } from "@/lib/format";

export function CapmAlphaTab() {
  const { result } = usePortfolio();
  const { stocks, market, riskFreeRate } = result;
  const rows = stocksForSML(stocks, market, riskFreeRate);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <div className="flex items-center gap-2 text-slate-900">
          <LineChartIcon size={20} className="text-brand-600" aria-hidden />
          <h3 className="text-xl font-semibold">Step 2 — Finding Alpha with CAPM</h3>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-slate-600">
          CAPM says each asset's fair return depends only on its sensitivity to market risk (β).
          Points <strong>above</strong> the Security Market Line are beating the fair return —
          that extra return is the stock's <strong>alpha</strong>. Alpha is why active allocation
          can beat the market.
        </p>
      </header>

      <section className="card p-5">
        <SMLChart stocks={stocks} market={market} riskFreeRate={riskFreeRate} />
      </section>

      <section className="card overflow-hidden">
        <div className="border-b border-slate-100 px-4 py-2.5 text-sm font-medium text-slate-700">
          Per-stock CAPM diagnostics
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Ticker
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Beta β
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  CAPM required E(r)
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Realized E(r)
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Alpha α
                </th>
                <th scope="col" className="px-4 py-2 text-left font-medium">
                  Assessment
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
              {rows.map((s) => {
                const required = capmRequiredReturn(market, riskFreeRate, s.beta);
                const isPositive = s.alpha > 0;
                return (
                  <tr key={s.ticker} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5 font-semibold text-slate-900">{s.ticker}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{decimals(s.beta, 2)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{pct(required, 2)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      {pct(s.expectedReturn, 2)}
                    </td>
                    <td
                      className={clsx(
                        "px-4 py-2.5 text-right font-semibold tabular-nums",
                        isPositive ? "text-emerald-600" : "text-rose-600",
                      )}
                    >
                      {signedPct(s.alpha)}
                    </td>
                    <td className="px-4 py-2.5 text-left text-xs">
                      <span
                        className={clsx(
                          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium",
                          isPositive
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-rose-50 text-rose-700",
                        )}
                      >
                        {isPositive ? (
                          <>
                            <Sparkles size={12} /> Undervalued
                          </>
                        ) : (
                          "Overvalued"
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
