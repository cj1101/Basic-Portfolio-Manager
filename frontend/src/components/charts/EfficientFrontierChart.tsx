import { useEffect, useMemo, useState } from "react";
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
import type { CovarianceMatrix, FrontierPoint, ORP, StockMetrics } from "@/types/contracts";
import { pct } from "@/lib/format";

export interface EfficientFrontierChartProps {
  frontier: FrontierPoint[];
  orp: ORP;
  stocks: StockMetrics[];
  covariance: CovarianceMatrix;
  height?: number;
}

const tooltipFormatter = (value: unknown) =>
  typeof value === "number" ? pct(value, 2) : String(value);

interface MarkowitzPoint extends FrontierPoint {
  isEfficient: boolean;
}

interface Domain {
  xMax: number;
  yMax: number;
}

function buildMarkowitzCurve(
  frontier: FrontierPoint[],
  stocks: StockMetrics[],
  covariance: CovarianceMatrix,
): MarkowitzPoint[] {
  if (frontier.length === 0 || stocks.length === 0 || covariance.matrix.length === 0) {
    return [];
  }

  const matrix = covariance.matrix;
  const meansByTicker = new Map(stocks.map((stock) => [stock.ticker, stock.expectedReturn]));
  const means = covariance.tickers.map((ticker) => meansByTicker.get(ticker) ?? 0);
  const n = means.length;

  if (matrix.length !== n || matrix.some((row) => row.length !== n)) {
    return frontier.map((point, index) => ({ ...point, isEfficient: index !== 0 }));
  }

  const solveLinear = (lhs: number[][], rhs: number[]): number[] | null => {
    const size = rhs.length;
    const aug = lhs.map((row, index) => [...row, rhs[index]]);
    for (let col = 0; col < size; col += 1) {
      let pivot = col;
      for (let row = col + 1; row < size; row += 1) {
        if (Math.abs(aug[row][col]) > Math.abs(aug[pivot][col])) {
          pivot = row;
        }
      }
      if (Math.abs(aug[pivot][col]) < 1e-12) {
        return null;
      }
      if (pivot !== col) {
        [aug[col], aug[pivot]] = [aug[pivot], aug[col]];
      }
      const pivotValue = aug[col][col];
      for (let j = col; j <= size; j += 1) {
        aug[col][j] /= pivotValue;
      }
      for (let row = 0; row < size; row += 1) {
        if (row === col) continue;
        const factor = aug[row][col];
        for (let j = col; j <= size; j += 1) {
          aug[row][j] -= factor * aug[col][j];
        }
      }
    }
    return aug.map((row) => row[size]);
  };

  const sigmaInvOnes = solveLinear(matrix, Array.from({ length: n }, () => 1));
  const sigmaInvMeans = solveLinear(matrix, means);
  if (!sigmaInvOnes || !sigmaInvMeans) {
    return frontier.map((point, index) => ({ ...point, isEfficient: index !== 0 }));
  }

  const aConst = sigmaInvOnes.reduce((sum, value) => sum + value, 0);
  const bConst = sigmaInvMeans.reduce((sum, value, index) => sum + value, 0);
  const cConst = means.reduce((sum, value, index) => sum + value * sigmaInvMeans[index], 0);
  const dConst = aConst * cConst - bConst * bConst;
  if (aConst <= 0 || dConst <= 1e-12) {
    return frontier.map((point, index) => ({ ...point, isEfficient: index !== 0 }));
  }

  const mvpExpectedReturn = bConst / aConst;
  const efficientMax = frontier.reduce((max, point) => Math.max(max, point.expectedReturn), 0);
  const upperSpan = Math.max(efficientMax - mvpExpectedReturn, 1e-6);
  const lowerTarget = 0;
  const upperTarget = efficientMax + upperSpan * 0.45;
  const samples = Math.max(80, frontier.length * 4);

  const points: MarkowitzPoint[] = [];
  for (let i = 0; i < samples; i += 1) {
    const t = samples === 1 ? 0 : i / (samples - 1);
    const expectedReturn = lowerTarget + t * (upperTarget - lowerTarget);
    const variance =
      (aConst * expectedReturn * expectedReturn - 2 * bConst * expectedReturn + cConst) / dConst;
    if (!Number.isFinite(variance) || variance < 0) {
      continue;
    }
    points.push({
      stdDev: Math.sqrt(variance),
      expectedReturn,
      isEfficient: expectedReturn >= mvpExpectedReturn,
    });
  }

  return points;
}

function computeDefaultDomain(
  points: FrontierPoint[],
  stocks: StockMetrics[],
  orp: ORP,
): Domain {
  const xValues = [...points.map((p) => p.stdDev), ...stocks.map((s) => s.stdDev), orp.stdDev];
  const yValues = [
    ...points.map((p) => p.expectedReturn),
    ...stocks.map((s) => s.expectedReturn),
    orp.expectedReturn,
  ];
  const xMax = Math.max(...xValues, 0);
  const yMax = Math.max(...yValues, 0);
  return {
    xMax: xMax * 1.1 + 0.01,
    yMax: yMax * 1.1 + 0.01,
  };
}

export function EfficientFrontierChart({
  frontier,
  orp,
  stocks,
  covariance,
  height = 420,
}: EfficientFrontierChartProps) {
  const markowitzCurve = useMemo(
    () => buildMarkowitzCurve(frontier, stocks, covariance),
    [frontier, stocks, covariance],
  );
  const efficientCurve = markowitzCurve.filter((point) => point.isEfficient);
  const inefficientCurve = markowitzCurve.filter((point) => !point.isEfficient);

  const defaultDomain = useMemo(
    () => computeDefaultDomain(markowitzCurve, stocks, orp),
    [markowitzCurve, stocks, orp],
  );
  const [domain, setDomain] = useState<Domain>(defaultDomain);
  useEffect(() => {
    setDomain(defaultDomain);
  }, [defaultDomain]);

  const zoomIn = () =>
    setDomain((current) => ({
      xMax: Math.max(defaultDomain.xMax * 0.35, current.xMax * 0.8),
      yMax: Math.max(defaultDomain.yMax * 0.35, current.yMax * 0.8),
    }));

  const zoomOut = () =>
    setDomain((current) => ({
      xMax: Math.min(defaultDomain.xMax * 3, current.xMax * 1.25),
      yMax: Math.min(defaultDomain.yMax * 3, current.yMax * 1.25),
    }));

  const resetZoom = () => setDomain(defaultDomain);

  const stockPoints = stocks.map((s) => ({
    ticker: s.ticker,
    stdDev: s.stdDev,
    expectedReturn: s.expectedReturn,
  }));

  return (
    <div role="img" aria-label="Efficient frontier with ORP and individual stocks">
      <div className="mb-3 flex items-center justify-end gap-2">
        <button
          type="button"
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
          onClick={zoomIn}
        >
          Zoom in
        </button>
        <button
          type="button"
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
          onClick={zoomOut}
        >
          Zoom out
        </button>
        <button
          type="button"
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
          onClick={resetZoom}
        >
          Reset
        </button>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart margin={{ top: 24, right: 48, bottom: 36, left: 28 }}>
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
            domain={[0, domain.xMax]}
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
            domain={[0, domain.yMax]}
          />
          <Tooltip
            formatter={tooltipFormatter}
            labelFormatter={() => ""}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend verticalAlign="top" height={28} iconSize={10} wrapperStyle={{ fontSize: 12 }} />

          <Line
            name="Efficient frontier"
            data={efficientCurve}
            type="monotone"
            dataKey="expectedReturn"
            stroke="#2563eb"
            strokeWidth={2.5}
            dot={{ r: 3, stroke: "#2563eb", fill: "#fff", strokeWidth: 1.5 }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
          />
          <Line
            name="Inefficient frontier"
            data={inefficientCurve}
            type="monotone"
            dataKey="expectedReturn"
            stroke="#94a3b8"
            strokeDasharray="6 4"
            strokeWidth={2}
            dot={false}
            activeDot={false}
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
            r={10}
            fill="#ef4444"
            stroke="#fff"
            strokeWidth={2}
            ifOverflow="extendDomain"
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
