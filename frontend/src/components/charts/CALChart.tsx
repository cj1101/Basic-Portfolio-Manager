import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ORP } from "@/types/contracts";
import type { CompletePortfolioDerivation } from "@/lib/completePortfolio";
import { calFromORP } from "@/lib/calFromORP";
import { pct } from "@/lib/format";

export interface CALChartProps {
  orp: ORP;
  riskFreeRate: number;
  complete: CompletePortfolioDerivation;
  height?: number;
}

export function CALChart({ orp, riskFreeRate, complete, height = 340 }: CALChartProps) {
  const yMax = Math.max(1.5, Math.ceil((complete.yStar + 0.3) * 10) / 10);
  const cal = calFromORP(orp, riskFreeRate, { yMax, steps: 20 });

  const yourPoint = {
    stdDev: complete.stdDev,
    expectedReturn: complete.expectedReturn,
  };

  return (
    <div role="img" aria-label="Capital Allocation Line with the investor's complete portfolio">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart margin={{ top: 10, right: 30, bottom: 28, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            type="number"
            dataKey="stdDev"
            domain={[0, "dataMax + 0.02"]}
            tickFormatter={(v: number) => pct(v, 0)}
            label={{
              value: "Standard Deviation σ (annualized)",
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
            domain={[0, "dataMax + 0.05"]}
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
            formatter={(v: unknown) => (typeof v === "number" ? pct(v, 2) : String(v))}
            labelFormatter={() => ""}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend verticalAlign="top" height={28} iconSize={10} wrapperStyle={{ fontSize: 12 }} />

          <ReferenceLine y={riskFreeRate} stroke="#94a3b8" strokeDasharray="4 4" />
          <Line
            name="Capital Allocation Line"
            data={cal}
            type="linear"
            dataKey="expectedReturn"
            stroke="#2563eb"
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />

          <ReferenceDot
            x={0}
            y={riskFreeRate}
            r={5}
            fill="#94a3b8"
            stroke="#fff"
            strokeWidth={2}
            label={{ value: "r_f", position: "left", fill: "#64748b", fontSize: 11 }}
          />
          <ReferenceDot
            x={orp.stdDev}
            y={orp.expectedReturn}
            r={6}
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
          <ReferenceDot
            x={yourPoint.stdDev}
            y={yourPoint.expectedReturn}
            r={8}
            fill="#22c55e"
            stroke="#fff"
            strokeWidth={2}
            label={{
              value: "Your Portfolio",
              position: "bottom",
              fill: "#16a34a",
              fontSize: 11,
              fontWeight: 600,
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
