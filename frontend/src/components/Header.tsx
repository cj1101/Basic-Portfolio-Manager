import { useState } from "react";
import { BrainCircuit, ShieldCheck, Target, AlertTriangle, Download, Loader2 } from "lucide-react";
import { Badge } from "./ui/Badge";
import { SettingsButton, SettingsPanel } from "./Settings";
import { usePortfolio } from "@/state/portfolioContext";
import { pct } from "@/lib/format";
import { exportPortfolio } from "@/lib/api";
import type { ExportRequest, ReturnFrequency } from "@/types/contracts";

function riskLabel(A: number): string {
  if (A <= 2) return "Aggressive";
  if (A <= 4) return "Moderate";
  if (A <= 6) return "Balanced";
  if (A <= 8) return "Conservative";
  return "Very Conservative";
}

function HistoricalWindowControls() {
  const {
    useHistoricalAsOf,
    setHistoricalAnalysisEnabled,
    asOfDate,
    setAsOfDate,
    lookbackYears,
    setLookbackYears,
    returnFrequency,
    setReturnFrequency,
  } = usePortfolio();

  const lookbackOptions = Array.from({ length: 20 }, (_, i) => i + 1);

  return (
    <div className="flex w-full max-w-2xl flex-wrap items-center gap-2 md:justify-end">
      <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-slate-500 bg-slate-800"
          checked={useHistoricalAsOf}
          onChange={(e) => setHistoricalAnalysisEnabled(e.target.checked)}
        />
        Historical window (not latest prices)
      </label>
      {useHistoricalAsOf ? (
        <>
          <label className="flex items-center gap-1 text-xs text-slate-400">
            End date
            <input
              type="date"
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-white"
            />
          </label>
          <label className="flex items-center gap-1 text-xs text-slate-400">
            Lookback
            <select
              value={lookbackYears}
              onChange={(e) => setLookbackYears(Number(e.target.value))}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-white"
            >
              {lookbackOptions.map((y) => (
                <option key={y} value={y}>
                  {y}y
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1 text-xs text-slate-400">
            Frequency
            <select
              value={returnFrequency}
              onChange={(e) => setReturnFrequency(e.target.value as ReturnFrequency)}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-white"
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
        </>
      ) : null}
    </div>
  );
}

function ExportButton() {
  const { tickers, optimizationRequest, riskProfile } = usePortfolio();
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    if (tickers.length === 0) return;
    setExporting(true);
    try {
      const blob = await exportPortfolio({
        tickers: optimizationRequest.tickers,
        riskProfile,
        returnFrequency: optimizationRequest.returnFrequency ?? "daily",
        lookbackYears: optimizationRequest.lookbackYears ?? 5,
        allowShort: optimizationRequest.allowShort ?? true,
        allowLeverage: optimizationRequest.allowLeverage ?? true,
        ...(optimizationRequest.asOf ? { asOf: optimizationRequest.asOf } : {}),
      } satisfies ExportRequest);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Portfolio_Analysis_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error("Export failed", err);
      alert("Export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleExport}
      disabled={exporting || tickers.length === 0}
      title="Export all data and calculations to Excel"
      className="flex items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {exporting ? (
        <Loader2 size={16} className="animate-spin text-brand-600" />
      ) : (
        <Download size={16} className="text-brand-600" />
      )}
      <span>{exporting ? "Generating Excel..." : "Export .xlsx"}</span>
    </button>
  );
}

export function Header() {
  const { riskProfile, result } = usePortfolio();
  const { riskAversion, targetReturn } = riskProfile;
  const leverage = result.complete.leverageUsed;
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <header
      className="bg-slate-900 text-white shadow-md"
      role="banner"
      aria-label="Portfolio Manager report header"
    >
      <div className="mx-auto flex max-w-6xl flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold md:text-3xl">
            <BrainCircuit className="text-brand-500" size={32} aria-hidden />
            <span>Portfolio Manager</span>
            <span className="hidden text-sm font-medium uppercase tracking-wider text-slate-400 md:inline">
              Client Report
            </span>
          </h1>
          <p className="mt-2 text-sm text-slate-400 md:text-base">
            Transparent, math-first portfolio construction along the Capital Allocation Line.
          </p>
        </div>
        <div className="flex flex-col gap-3 md:items-end">
          <div className="flex flex-wrap items-center gap-2 md:justify-end">
            <Badge
              tone="success"
              icon={<ShieldCheck size={16} aria-hidden />}
              className="!border-emerald-400/40 !bg-slate-800 !text-emerald-300"
            >
              Risk profile: {riskLabel(riskAversion)} (A&nbsp;=&nbsp;{riskAversion})
            </Badge>
            <Badge
              tone="brand"
              icon={<Target size={16} aria-hidden />}
              className="!border-violet-400/40 !bg-slate-800 !text-violet-300"
            >
              Target: {targetReturn != null ? pct(targetReturn, 1) : "—"} annualized
            </Badge>
            {leverage ? (
              <Badge
                tone="warn"
                icon={<AlertTriangle size={16} aria-hidden />}
                className="!border-amber-400/40 !bg-slate-800 !text-amber-300"
              >
                Leverage in use
              </Badge>
            ) : null}
          </div>
          <HistoricalWindowControls />
          <div className="flex flex-wrap items-center gap-2 md:justify-end">
            <div className="flex items-center gap-2 border-t border-slate-700 pt-2 md:border-t-0 md:border-l md:pt-0 md:pl-2">
              <ExportButton />
              <SettingsButton onOpen={() => setSettingsOpen(true)} />
            </div>
          </div>
        </div>
      </div>
      {settingsOpen ? <SettingsPanel onClose={() => setSettingsOpen(false)} /> : null}
    </header>
  );
}
