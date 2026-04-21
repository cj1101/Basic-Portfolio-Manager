import clsx from "clsx";
import { useEffect, useId, useState } from "react";

export interface NumberInputProps {
  /** Current value as an annualized decimal (e.g. `0.15` for 15%). */
  value: number | undefined;
  /** Called with the new annualized decimal value, or `undefined` if cleared. */
  onChange: (v: number | undefined) => void;
  label: string;
  placeholder?: string;
  /**
   * Display mode:
   *   - `percent` — the user types a percent (e.g. `15`), we store `0.15`
   *   - `decimal` — the user types the raw decimal (e.g. `0.15`)
   */
  mode?: "percent" | "decimal";
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  helperText?: string;
  className?: string;
  id?: string;
}

/**
 * Percent-mode input keeps annualized decimals in state (per quant.mdc §1) but
 * lets the user type percent numbers in the UI. The conversion happens ONLY
 * at this boundary.
 */
export function NumberInput({
  value,
  onChange,
  label,
  placeholder,
  mode = "percent",
  min,
  max,
  step,
  suffix,
  helperText,
  className,
  id,
}: NumberInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  const toDisplay = (v: number | undefined): string => {
    if (v == null || !Number.isFinite(v)) return "";
    if (mode === "percent") return (v * 100).toString();
    return v.toString();
  };

  const [raw, setRaw] = useState<string>(toDisplay(value));

  useEffect(() => {
    setRaw(toDisplay(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, mode]);

  const commit = (next: string) => {
    if (next.trim() === "") {
      onChange(undefined);
      return;
    }
    const parsed = Number(next);
    if (!Number.isFinite(parsed)) return;
    const asDecimal = mode === "percent" ? parsed / 100 : parsed;
    onChange(asDecimal);
  };

  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <label htmlFor={inputId} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          type="number"
          inputMode="decimal"
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              commit((e.target as HTMLInputElement).value);
            }
          }}
          placeholder={placeholder}
          min={min}
          max={max}
          step={step}
          className={clsx(
            "form-input w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 text-sm text-slate-900 shadow-sm transition-colors",
            "hover:border-slate-400 focus:border-brand-500",
            suffix ? "pr-10" : "pr-3",
          )}
        />
        {suffix ? (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm font-medium text-slate-400">
            {suffix}
          </span>
        ) : null}
      </div>
      {helperText ? <p className="text-xs text-slate-500">{helperText}</p> : null}
    </div>
  );
}
