import { useState } from "react";
import { BrainCircuit, ShieldCheck, Target, AlertTriangle } from "lucide-react";
import { Badge } from "./ui/Badge";
import { SettingsButton, SettingsPanel } from "./Settings";
import { usePortfolio } from "@/state/portfolioContext";
import { pct } from "@/lib/format";

function riskLabel(A: number): string {
  if (A <= 2) return "Aggressive";
  if (A <= 4) return "Moderate";
  if (A <= 6) return "Balanced";
  if (A <= 8) return "Conservative";
  return "Very Conservative";
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
        <div className="flex flex-wrap items-center gap-2">
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
          <SettingsButton onOpen={() => setSettingsOpen(true)} />
        </div>
      </div>
      {settingsOpen ? <SettingsPanel onClose={() => setSettingsOpen(false)} /> : null}
    </header>
  );
}
