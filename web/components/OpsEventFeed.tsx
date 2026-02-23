import Link from "next/link";

import {Card, StatusBadge} from "@/components/ui";

export type OpsEvent = {
  timestamp: string;
  level: "info" | "warning" | "error";
  component: string;
  event_type: string;
  message: string;
  correlation_id?: string | null;
  payload?: Record<string, unknown>;
};

const LEVEL_VARIANT: Record<OpsEvent["level"], "info" | "warning" | "error"> = {
  info: "info",
  warning: "warning",
  error: "error",
};

export function OpsEventFeed({
  title,
  emptyState,
  events,
  clearFiltersHref,
  clearFiltersLabel,
}: {
  title: string;
  emptyState: string;
  events: OpsEvent[];
  clearFiltersHref?: string;
  clearFiltersLabel?: string;
}) {
  return (
    <Card>
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      {events.length === 0 ? (
        <div className="space-y-2">
          <p className="text-sm text-gray-500 dark:text-slate-400">{emptyState}</p>
          {clearFiltersHref && clearFiltersLabel && (
            <Link
              href={clearFiltersHref}
              className="inline-flex rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {clearFiltersLabel}
            </Link>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {events.map((event, index) => (
            <div
              key={`${event.timestamp}-${event.event_type}-${index}`}
              className="rounded-md border border-gray-200 px-3 py-2 dark:border-slate-700"
            >
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge label={event.level} variant={LEVEL_VARIANT[event.level]} />
                <span className="font-mono text-xs text-gray-500 dark:text-slate-400">
                  {event.timestamp}
                </span>
                <span className="text-xs text-gray-500 dark:text-slate-400">{event.component}</span>
              </div>
              <p className="mt-1 text-sm font-medium">{event.event_type}</p>
              <p className="text-sm text-gray-600 dark:text-slate-400">{event.message}</p>
              {event.correlation_id && (
                <p className="mt-1 font-mono text-xs text-gray-500 dark:text-slate-400">
                  correlation: {event.correlation_id}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
