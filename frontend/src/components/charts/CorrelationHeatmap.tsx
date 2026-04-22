import type { CorrelationMatrix } from "@/types/contracts";
import { decimals } from "@/lib/format";

const GREEN: [number, number, number] = [22, 101, 52];
const WHITE: [number, number, number] = [255, 255, 255];
const RED: [number, number, number] = [153, 27, 27];

function blend(a: [number, number, number], b: [number, number, number], t: number): string {
  const u = Math.min(1, Math.max(0, t));
  const r = Math.round(a[0]! + (b[0]! - a[0]!) * u);
  const g = Math.round(a[1]! + (b[1]! - a[1]!) * u);
  const bl = Math.round(a[2]! + (b[2]! - a[2]!) * u);
  return `rgb(${r} ${g} ${bl})`;
}

/** Map ρ in [-1, 1] to a green (-1) → white (0) → red (+1) background. */
export function correlationCellBackground(rho: number): string {
  if (rho <= 0) {
    const t = 1 + rho;
    return blend(GREEN, WHITE, t);
  }
  return blend(WHITE, RED, rho);
}

export function CorrelationHeatmap({ correlation }: { correlation: CorrelationMatrix | undefined }) {
  if (correlation == null || !correlation.matrix.length || !correlation.tickers.length) {
    return (
      <p className="text-sm text-slate-500" role="status">
        Correlation data is not available. Re-run optimization or refresh the page.
      </p>
    );
  }
  const { tickers, matrix } = correlation;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[20rem] border-collapse text-sm" role="table" aria-label="Asset correlation matrix">
        <thead>
          <tr>
            <th
              scope="col"
              className="bg-slate-50 px-2 py-1.5 text-left text-xs font-medium text-slate-500"
            />
            {tickers.map((t) => (
              <th
                key={t}
                scope="col"
                className="bg-slate-50 px-2 py-1.5 text-center text-xs font-semibold text-slate-800"
              >
                {t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => {
            const rowTicker = tickers[i] ?? "";
            return (
              <tr key={rowTicker}>
                <th
                  scope="row"
                  className="whitespace-nowrap bg-slate-50 px-2 py-1.5 text-left text-xs font-semibold text-slate-800"
                >
                  {rowTicker}
                </th>
                {row.map((rho, j) => {
                  const colTicker = tickers[j] ?? "";
                  return (
                    <td
                      key={`${rowTicker}-${colTicker}`}
                      className="border border-slate-200/80 px-1 py-1 text-center tabular-nums"
                      style={{ backgroundColor: correlationCellBackground(rho) }}
                      title={`Correlation ${rowTicker} vs ${colTicker}: ${decimals(rho, 3)}`}
                    >
                      <span className="text-slate-900">{decimals(rho, 2)}</span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500" aria-hidden>
        Scale: −1 (green, diversification) → 0 (neutral) → +1 (red, co-movement).
      </p>
    </div>
  );
}
