import type { PropsWithChildren, ReactNode } from "react";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  children,
}: PropsWithChildren<EmptyStateProps>) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center">
      {icon ? <div className="text-slate-400">{icon}</div> : null}
      <h3 className="text-base font-semibold text-slate-800">{title}</h3>
      {description ? (
        <p className="max-w-md text-sm text-slate-500">{description}</p>
      ) : null}
      {children}
    </div>
  );
}
