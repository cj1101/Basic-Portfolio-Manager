import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Ticker } from "@/types/contracts";
import { pct } from "@/lib/format";

export interface WeightsBarChartProps {
  weights: Record<Ticker, number>;
  /** Weight of the risk-free asset (1 - y). Negative when leveraged. */
  riskFreeWeight?: number;
  height?: number;
}

export function WeightsBarChart({ weights, riskFreeWeight, height = 300 }: WeightsBarChartProps) {
  const rows: { ticker: string; weight: number; isRiskFree?: boolean }[] = Object.entries(weights)
    .map(([ticker, weight]) => ({ ticker, weight }))
    .sort((a, b) => b.weight - a.weight);

  if (riskFreeWeight != null) {
    rows.push({ ticker: "Risk-free", weight: riskFreeWeight, isRiskFree: true });
  }

  return (
    <div role="img" aria-label="Portfolio weights by position">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 10, right: 30, bottom: 10, left: 40 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
          <XAxis
            type="number"
            tickFormatter={(v: number) => pct(v, 0)}
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
            domain={[(dataMin: number) => Math.min(0, dataMin), (dataMax: number) => Math.max(1, dataMax)]}
          />
          <YAxis
            type="category"
            dataKey="ticker"
            stroke="#94a3b8"
            tick={{ fontSize: 12, fontWeight: 600 }}
            width={80}
          />
          <Tooltip
            formatter={(v: unknown) => (typeof v === "number" ? pct(v, 2) : String(v))}
            contentStyle={{ fontSize: 12 }}
          />
          <ReferenceLine x={0} stroke="#64748b" />
          <Bar dataKey="weight" radius={[0, 4, 4, 0]}>
            {rows.map((r) => {
              const fill = r.isRiskFree
                ? r.weight >= 0
                  ? "#94a3b8"
                  : "#f97316"
                : r.weight >= 0
                  ? "#2563eb"
                  : "#ef4444";
              return <Cell key={r.ticker} fill={fill} />;
            })}
            <LabelList
              dataKey="weight"
              position="right"
              formatter={(v: unknown) => (typeof v === "number" ? pct(v, 1) : "")}
              style={{ fill: "#334155", fontSize: 11, fontWeight: 600 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
