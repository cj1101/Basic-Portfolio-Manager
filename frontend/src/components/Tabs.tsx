import clsx from "clsx";
import {
  BarChart3,
  Compass,
  LineChart as LineChartIcon,
  PieChart,
  Database,
  type LucideIcon,
} from "lucide-react";

export type TabId = "overview" | "frontier" | "capm" | "allocation" | "data";

export interface TabDefinition {
  id: TabId;
  label: string;
  shortLabel: string;
  Icon: LucideIcon;
}

// eslint-disable-next-line react-refresh/only-export-components
export const TABS: TabDefinition[] = [
  {
    id: "overview",
    label: "Executive Summary",
    shortLabel: "Overview",
    Icon: BarChart3,
  },
  {
    id: "frontier",
    label: "1. The Efficient Frontier",
    shortLabel: "Frontier",
    Icon: Compass,
  },
  {
    id: "capm",
    label: "2. Finding Alpha (CAPM)",
    shortLabel: "CAPM / Alpha",
    Icon: LineChartIcon,
  },
  {
    id: "allocation",
    label: "3. Asset Allocation",
    shortLabel: "Allocation",
    Icon: PieChart,
  },
  {
    id: "data",
    label: "APIs & Data Sources",
    shortLabel: "Data",
    Icon: Database,
  },
];

export interface TabsProps {
  value: TabId;
  onChange: (id: TabId) => void;
}

export function Tabs({ value, onChange }: TabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Report sections"
      className="mb-8 flex flex-wrap gap-2 border-b border-slate-200 pb-2"
    >
      {TABS.map(({ id, label, Icon }) => {
        const active = value === id;
        return (
          <button
            key={id}
            role="tab"
            id={`tab-${id}`}
            aria-selected={active}
            aria-controls={`panel-${id}`}
            type="button"
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(id)}
            className={clsx(
              "inline-flex items-center gap-2 rounded-t-lg px-4 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-brand-600 text-white shadow-sm"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800",
            )}
          >
            <Icon size={15} aria-hidden />
            {label}
          </button>
        );
      })}
    </div>
  );
}
