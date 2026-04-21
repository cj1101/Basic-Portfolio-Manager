import clsx from "clsx";
import type { ReactNode } from "react";

export interface KpiCardProps {
  label: string;
  value: string;
  sublabel?: string;
  icon?: ReactNode;
  tone?: "neutral" | "positive" | "negative" | "brand";
  className?: string;
}

const TONE: Record<NonNullable<KpiCardProps["tone"]>, string> = {
  neutral: "",
  positive: "text-emerald-600",
  negative: "text-rose-600",
  brand: "text-brand-700",
};

export function KpiCard({ label, value, sublabel, icon, tone = "neutral", className }: KpiCardProps) {
  return (
    <div className={clsx("card flex flex-col gap-2 p-5", className)}>
      <div className="flex items-center justify-between">
        <span className="stat-label">{label}</span>
        {icon ? <span className="text-slate-400">{icon}</span> : null}
      </div>
      <div className={clsx("stat-value", TONE[tone])}>{value}</div>
      {sublabel ? <p className="text-xs text-slate-500">{sublabel}</p> : null}
    </div>
  );
}
