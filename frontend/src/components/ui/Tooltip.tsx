import clsx from "clsx";
import { useId, useState, type PropsWithChildren } from "react";

export interface TooltipProps {
  label: string;
  placement?: "top" | "bottom";
  className?: string;
  contentClassName?: string;
}

/**
 * Minimal CSS-only tooltip — appears on hover/focus of the wrapped element.
 * Not a fully-featured a11y tooltip (no escape key handling, no portal), but
 * adequate for inline help strings. Uses `role="tooltip"` and `aria-describedby`.
 */
export function Tooltip({
  label,
  placement = "top",
  className,
  contentClassName,
  children,
}: PropsWithChildren<TooltipProps>) {
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <span className={clsx("group relative inline-flex", className)}>
      <span
        aria-describedby={id}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex items-center"
      >
        {children}
      </span>
      {open ? (
        <span
          id={id}
          role="tooltip"
          className={clsx(
            "pointer-events-none absolute left-1/2 z-30 w-max max-w-sm -translate-x-1/2 rounded-md bg-slate-900 px-2.5 py-1.5 text-xs leading-relaxed text-white shadow-lg",
            placement === "top" ? "bottom-full mb-2" : "top-full mt-2",
            contentClassName,
          )}
        >
          {label}
        </span>
      ) : null}
    </span>
  );
}
