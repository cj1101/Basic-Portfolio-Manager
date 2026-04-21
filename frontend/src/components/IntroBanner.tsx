import { Info } from "lucide-react";

export function IntroBanner() {
  return (
    <div
      role="note"
      className="mb-8 flex items-start gap-3 rounded-r-lg border-l-4 border-brand-500 bg-brand-50 p-4 shadow-sm"
    >
      <Info className="mt-0.5 shrink-0 text-brand-500" size={20} aria-hidden />
      <p className="text-sm leading-relaxed text-slate-700">
        <strong>How to read this report: </strong>
        Your Portfolio Manager processes 5 years of daily data using Modern Portfolio Theory and
        the Single-Index Model. Every tab below explains one step of the decision pipeline that
        turns your ticker list and risk profile into a mathematically optimal allocation along the
        Capital Allocation Line.
      </p>
    </div>
  );
}
