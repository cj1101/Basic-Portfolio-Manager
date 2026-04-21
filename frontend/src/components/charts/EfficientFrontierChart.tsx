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
import type { FrontierPoint, ORP, StockMetrics } from "@/types/contracts";
import { pct } from "@/lib/format";

export interface EfficientFrontierChartProps {
  frontier: FrontierPoint[];
  orp: ORP;
  stocks: StockMetrics[];
  height?: number;
}

const tooltipFormatter = (value: unknown) =>
  typeof value === "number" ? pct(value, 2) : String(value);

export function EfficientFrontierChart({
  frontier,
  orp,
  stocks,
  height = 340,
}: EfficientFrontierChartProps) {
  const stockPoints = stocks.map((s) => ({
    ticker: s.ticker,
    stdDev: s.stdDev,
    expectedReturn: s.expectedReturn,
  }));

  return (
    <div role="img" aria-label="Efficient frontier with ORP and individual stocks">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart margin={{ top: 10, right: 30, bottom: 28, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            type="number"
            dataKey="stdDev"
            tickFormatter={(v: number) => pct(v, 0)}
            label={{
              value: "Standard Deviation σ (annualized)",
              position: "insideBottom",
              offset: -10,
              style: { fill: "#475569", fontSize: 12 },
            }}
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
            domain={["dataMin - 0.02", "dataMax + 0.04"]}
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
            domain={["dataMin - 0.02", "dataMax + 0.05"]}
          />
          <Tooltip
            formatter={tooltipFormatter}
            labelFormatter={() => ""}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend verticalAlign="top" height={28} iconSize={10} wrapperStyle={{ fontSize: 12 }} />

          <Line
            name="Efficient frontier"
            data={frontier}
            type="monotone"
            dataKey="expectedReturn"
            stroke="#2563eb"
            strokeWidth={2.5}
            dot={{ r: 3, stroke: "#2563eb", fill: "#fff", strokeWidth: 1.5 }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
          />
          <Scatter
            name="Individual stocks"
            data={stockPoints}
            fill="#64748b"
            shape="circle"
          />
          <ReferenceDot
            x={orp.stdDev}
            y={orp.expectedReturn}
            r={8}
            fill="#ef4444"
            stroke="#fff"
            strokeWidth={2}
            label={{
              value: "ORP",
              position: "top",
              fill: "#ef4444",
              fontSize: 11,
              fontWeight: 600,
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
