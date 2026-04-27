import { useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceDot,
} from "recharts";
import type { PriceBar } from "@/types/contracts";

export interface MovingAverageChartProps {
  bars: PriceBar[];
  height?: number;
  ticker: string;
  /** Controlled window size. If provided, local state is ignored. */
  windowSize?: number;
  onWindowSizeChange?: (w: number) => void;
}

const usdFormatter = (value: number) => `$${value.toFixed(2)}`;

interface DataPoint {
  date: string;
  price: number;
  ma: number | null;
  crossover: "bullish" | "bearish" | null;
}

export function MovingAverageChart({
  bars,
  ticker,
  height = 400,
  windowSize: controlledWindow,
  onWindowSizeChange,
}: MovingAverageChartProps) {
  const [localWindowSize, setLocalWindowSize] = useState<number>(50);
  const windowSize = controlledWindow ?? localWindowSize;
  const setWindowSize = (w: number) => {
    setLocalWindowSize(w);
    onWindowSizeChange?.(w);
  };

  const data = useMemo(() => {
    const points: DataPoint[] = [];
    if (!bars || bars.length === 0) return points;

    // Assumes bars are chronologically sorted (oldest to newest)
    // If not, we should sort them, but backend usually returns chronologically.
    const sortedBars = [...bars].sort((a, b) => a.date.localeCompare(b.date));

    let prevPriceOverMA: boolean | null = null;

    for (let i = 0; i < sortedBars.length; i++) {
      const bar = sortedBars[i]!;
      const price = bar.close;
      let ma: number | null = null;
      let crossover: "bullish" | "bearish" | null = null;

      if (i >= windowSize - 1) {
        let sum = 0;
        for (let j = 0; j < windowSize; j++) {
          sum += sortedBars[i - j]!.close;
        }
        ma = sum / windowSize;

        const currentPriceOverMA = price > ma;
        if (prevPriceOverMA !== null && currentPriceOverMA !== prevPriceOverMA) {
          crossover = currentPriceOverMA ? "bullish" : "bearish";
        }
        prevPriceOverMA = currentPriceOverMA;
      }

      points.push({
        date: bar.date,
        price,
        ma,
        crossover,
      });
    }

    return points;
  }, [bars, windowSize]);

  const bullishCrossovers = data.filter((d) => d.crossover === "bullish");
  const bearishCrossovers = data.filter((d) => d.crossover === "bearish");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">
          Moving Average & Crossovers ({ticker})
        </h3>
        <div className="flex items-center gap-3">
          <label htmlFor="ma-window" className="text-xs font-medium text-slate-600">
            Window: {windowSize} days
          </label>
          <input
            id="ma-window"
            type="range"
            min="5"
            max="100"
            step="1"
            value={windowSize}
            onChange={(e) => setWindowSize(parseInt(e.target.value, 10))}
            className="w-32 accent-brand-600"
          />
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
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
            tickFormatter={usdFormatter}
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
            label={{ value: "Price", angle: -90, position: "insideLeft", offset: 10, style: { fill: "#475569", fontSize: 12 } }}
          />
          <Tooltip
            formatter={(val: number, name: string) => [usdFormatter(val), name === "price" ? "Price" : `SMA (${windowSize})`]}
            labelFormatter={(label) => new Date(label as string).toLocaleDateString()}
            contentStyle={{ fontSize: 12, borderRadius: "6px" }}
          />
          <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: 12 }} />

          <Line
            name="price"
            type="monotone"
            dataKey="price"
            stroke="#94a3b8"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            name="ma"
            type="monotone"
            dataKey="ma"
            stroke="#2563eb"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />

          {bullishCrossovers.map((c, i) => (
            <ReferenceDot
              key={`bull-${i}`}
              x={c.date}
              y={c.ma!}
              r={4}
              fill="#22c55e"
              stroke="#fff"
              strokeWidth={1}
            />
          ))}
          {bearishCrossovers.map((c, i) => (
            <ReferenceDot
              key={`bear-${i}`}
              x={c.date}
              y={c.ma!}
              r={4}
              fill="#ef4444"
              stroke="#fff"
              strokeWidth={1}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex gap-4 text-xs text-slate-500 justify-center">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-green-500 border border-white"></span> Bullish Crossover
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-red-500 border border-white"></span> Bearish Crossover
        </span>
      </div>
    </div>
  );
}
