"use client";

import {useState} from "react";
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

function hasPayload(payload: Record<string, unknown> | undefined): payload is Record<string, unknown> {
  return !!payload && Object.keys(payload).length > 0;
}

function EventPayload({payload}: {payload: Record<string, unknown>}) {
  const traceback = typeof payload.traceback === "string" ? payload.traceback : null;
  const rest = Object.fromEntries(
    Object.entries(payload).filter(([k]) => k !== "traceback"),
  );
  const hasRest = Object.keys(rest).length > 0;

  return (
    <div className="mt-2 space-y-2">
      {hasRest && (
        <div className="rounded bg-gray-50 px-3 py-2 dark:bg-slate-800/60">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            {Object.entries(rest).map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="font-medium text-gray-500 dark:text-slate-400">{key}</dt>
                <dd className="font-mono text-gray-700 break-all dark:text-slate-300">
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      {traceback && (
        <pre className="max-h-64 overflow-auto rounded bg-red-50 px-3 py-2 font-mono text-xs leading-relaxed text-red-800 dark:bg-red-950/30 dark:text-red-300">
          {traceback}
        </pre>
      )}
    </div>
  );
}

function EventRow({event}: {event: OpsEvent}) {
  const showToggle = hasPayload(event.payload);
  const autoExpand = event.level === "error" && showToggle;
  const [expanded, setExpanded] = useState(autoExpand);

  return (
    <div className="rounded-md border border-gray-200 px-3 py-2 dark:border-slate-700">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge label={event.level} variant={LEVEL_VARIANT[event.level]} />
        <span className="font-mono text-xs text-gray-500 dark:text-slate-400">
          {event.timestamp}
        </span>
        <span className="text-xs text-gray-500 dark:text-slate-400">{event.component}</span>
        {showToggle && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="ml-auto rounded px-2 py-0.5 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
          >
            {expanded ? "▾ Hide detail" : "▸ Show detail"}
          </button>
        )}
      </div>
      <p className="mt-1 text-sm font-medium">{event.event_type}</p>
      <p className="text-sm text-gray-600 dark:text-slate-400">{event.message}</p>
      {event.correlation_id && (
        <p className="mt-1 font-mono text-xs text-gray-500 dark:text-slate-400">
          correlation: {event.correlation_id}
        </p>
      )}
      {expanded && event.payload && <EventPayload payload={event.payload} />}
    </div>
  );
}

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
            <EventRow
              key={`${event.timestamp}-${event.event_type}-${index}`}
              event={event}
            />
          ))}
        </div>
      )}
    </Card>
  );
}
