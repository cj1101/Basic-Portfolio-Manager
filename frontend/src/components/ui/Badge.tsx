import clsx from "clsx";
import type { PropsWithChildren, ReactNode } from "react";

export interface BadgeProps {
  icon?: ReactNode;
  tone?: "neutral" | "info" | "success" | "warn" | "danger" | "brand";
  className?: string;
}

const TONE_STYLES: Record<NonNullable<BadgeProps["tone"]>, string> = {
  neutral: "bg-slate-100 text-slate-700 border-slate-200",
  info: "bg-sky-50 text-sky-700 border-sky-200",
  success: "bg-emerald-50 text-emerald-700 border-emerald-200",
  warn: "bg-amber-50 text-amber-700 border-amber-200",
  danger: "bg-rose-50 text-rose-700 border-rose-200",
  brand: "bg-brand-50 text-brand-700 border-brand-100",
};

export function Badge({
  icon,
  tone = "neutral",
  className,
  children,
}: PropsWithChildren<BadgeProps>) {
  return (
    <span className={clsx("chip", TONE_STYLES[tone], className)}>
      {icon}
      <span>{children}</span>
    </span>
  );
}
