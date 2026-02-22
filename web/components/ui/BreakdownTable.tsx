import {ReactNode} from "react";

import {Card} from "./Card";

export type BreakdownItem = {
  key: string;
  label: ReactNode;
  value: number;
  displayValue?: string;
};

type Props = {
  title: string;
  items: BreakdownItem[];
  maxValue?: number;
  className?: string;
};

export function BreakdownTable({title, items, maxValue, className = ""}: Props) {
  const max = maxValue ?? Math.max(...items.map((i) => i.value), 1);

  return (
    <Card className={className}>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400">
        {title}
      </h3>
      <div className="space-y-1.5">
        {items.map((item) => {
          const pct = max > 0 ? (item.value / max) * 100 : 0;
          return (
            <div key={item.key} className="group relative">
              <div
                className="absolute inset-y-0 start-0 rounded bg-accent/10 transition-all dark:bg-accent/20"
                style={{width: `${pct}%`}}
              />
              <div className="relative flex items-center justify-between px-3 py-1.5 text-sm">
                <span className="truncate font-medium">{item.label}</span>
                <span className="ms-2 tabular-nums text-gray-600 dark:text-slate-300">
                  {item.displayValue ?? item.value.toLocaleString()}
                </span>
              </div>
            </div>
          );
        })}
        {items.length === 0 && (
          <p className="py-4 text-center text-sm text-gray-400 dark:text-slate-500">
            No data
          </p>
        )}
      </div>
    </Card>
  );
}
