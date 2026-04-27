import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PriceBar } from "@/types/contracts";

export interface RelativeStrengthChartProps {
  stockBars: PriceBar[];
  benchmarkBars: PriceBar[];
  stockTicker: string;
  benchmarkTicker: string;
  height?: number;
}

interface DataPoint {
  date: string;
  ratio: number;
}

export function RelativeStrengthChart({
  stockBars,
  benchmarkBars,
  stockTicker,
  benchmarkTicker,
  height = 300,
}: RelativeStrengthChartProps) {
  const data = useMemo(() => {
    if (!stockBars?.length || !benchmarkBars?.length) return [];

    const benchmarkMap = new Map(benchmarkBars.map((b) => [b.date, b.close]));
    
    const points: DataPoint[] = [];
    const sortedStockBars = [...stockBars].sort((a, b) => a.date.localeCompare(b.date));

    for (const stockBar of sortedStockBars) {
      const benchmarkClose = benchmarkMap.get(stockBar.date);
      if (benchmarkClose && benchmarkClose > 0) {
        points.push({
          date: stockBar.date,
          ratio: stockBar.close / benchmarkClose,
        });
      }
    }
    return points;
  }, [stockBars, benchmarkBars]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h3 className="text-sm font-semibold text-slate-800">
          Relative Strength ({stockTicker} vs {benchmarkTicker})
        </h3>
        <p className="text-xs text-slate-500">
          An upward slope indicates that {stockTicker} is outperforming {benchmarkTicker}. A downward slope indicates underperformance.
        </p>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tickFormatter={(val) => {
              const d = new Date(val);
              return isNaN(d.valueOf()) ? "" : d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
            }}
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
            minTickGap={30}
          />
          <YAxis
            type="number"
            domain={["auto", "auto"]}
            tickFormatter={(val) => val.toFixed(4)}
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
            label={{ value: "Ratio", angle: -90, position: "insideLeft", offset: 10, style: { fill: "#475569", fontSize: 12 } }}
          />
          <Tooltip
            formatter={(val: number) => [val.toFixed(4), "RS Ratio"]}
            labelFormatter={(label) => new Date(label as string).toLocaleDateString()}
            contentStyle={{ fontSize: 12, borderRadius: "6px" }}
          />
          <Line
            type="monotone"
            dataKey="ratio"
            stroke="#8b5cf6"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
