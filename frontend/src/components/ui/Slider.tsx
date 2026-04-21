import clsx from "clsx";
import { useId, type CSSProperties } from "react";

export interface SliderProps {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  label: string;
  helperText?: string;
  marks?: readonly { value: number; label: string }[];
  className?: string;
  id?: string;
}

/**
 * Accessible styled range-input. Uses the `.slider-brand` class from index.css
 * and exposes the progress to CSS via the `--slider-progress` custom property.
 */
export function Slider({
  value,
  min,
  max,
  step = 1,
  onChange,
  label,
  helperText,
  marks,
  className,
  id,
}: SliderProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  const progressPct = ((value - min) / (max - min)) * 100;
  const style: CSSProperties = {
    ["--slider-progress" as string]: `${progressPct}%`,
  };

  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <label htmlFor={inputId} className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="font-mono text-sm tabular-nums text-slate-900">{value}</span>
      </label>
      <input
        id={inputId}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="slider-brand"
        style={style}
        aria-valuenow={value}
        aria-valuemin={min}
        aria-valuemax={max}
      />
      {marks ? (
        <div className="flex justify-between px-0.5 text-[10px] uppercase tracking-wide text-slate-400">
          {marks.map((m) => (
            <span key={m.value}>{m.label}</span>
          ))}
        </div>
      ) : null}
      {helperText ? <p className="text-xs text-slate-500">{helperText}</p> : null}
    </div>
  );
}
