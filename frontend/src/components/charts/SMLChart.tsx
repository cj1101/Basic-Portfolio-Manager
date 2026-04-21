import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MarketMetrics, StockMetrics } from "@/types/contracts";
import { pct } from "@/lib/format";
import { smlLine, stocksForSML } from "@/lib/sml";

export interface SMLChartProps {
  stocks: StockMetrics[];
  market: MarketMetrics;
  riskFreeRate: number;
  height?: number;
}

export function SMLChart({ stocks, market, riskFreeRate, height = 340 }: SMLChartProps) {
  const line = smlLine(market, riskFreeRate, 2.2);
  const points = stocksForSML(stocks, market, riskFreeRate);

  return (
    <div role="img" aria-label="Security Market Line with stocks colored by alpha sign">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart margin={{ top: 10, right: 30, bottom: 28, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            type="number"
            dataKey="beta"
            domain={[0, 2.2]}
            tickFormatter={(v: number) => v.toFixed(1)}
            label={{
              value: "Beta (β)",
              position: "insideBottom",
              offset: -10,
              style: { fill: "#475569", fontSize: 12 },
            }}
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
          />
          <YAxis
            type="number"
            dataKey="expectedReturn"
            tickFormatter={(v: number) => pct(v, 0)}
            label={{
              value: "Expected Return E(r)",
              angle: -90,
              position: "insideLeft",
              offset: 10,
              style: { fill: "#475569", fontSize: 12 },
            }}
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
          />
          <Tooltip
            formatter={(v: unknown, key: string) => {
              if (typeof v !== "number") return String(v);
              if (key === "beta") return v.toFixed(2);
              return pct(v, 2);
            }}
            labelFormatter={() => ""}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend verticalAlign="top" height={28} iconSize={10} wrapperStyle={{ fontSize: 12 }} />

          <Line
            name="Security Market Line"
            data={line}
            type="linear"
            dataKey="expectedReturn"
            stroke="#64748b"
            strokeDasharray="6 4"
            strokeWidth={2}
            dot={false}
            activeDot={false}
            isAnimationActive={false}
          />
          <Scatter
            name="Stocks with α > 0 (undervalued)"
            data={points.filter((p) => p.alpha > 0)}
            fill="#22c55e"
            shape="circle"
          />
          <Scatter
            name="Stocks with α < 0 (overvalued)"
            data={points.filter((p) => p.alpha <= 0)}
            fill="#ef4444"
            shape="circle"
          />
          <ReferenceDot
            x={1}
            y={market.expectedReturn}
            r={5}
            fill="#2563eb"
            stroke="#fff"
            strokeWidth={2}
            label={{
              value: "Market",
              position: "top",
              fill: "#2563eb",
              fontSize: 11,
              fontWeight: 600,
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
