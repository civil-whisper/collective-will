"use client";

import {useState, useEffect, useCallback} from "react";
import {useTranslations, useLocale} from "next-intl";
import {useSearchParams} from "next/navigation";
import Link from "next/link";

import {apiGet} from "@/lib/api";
import {
  type EvidenceEntry,
  type EvidenceResponse,
  type FilterCategory,
  EVENT_CATEGORIES,
  isDeliberationEvent,
  eventDescription,
  entityLink,
  relativeTime,
} from "@/lib/evidence";
import {PageShell, ChainStatusBadge, Card} from "@/components/ui";

const FILTER_LABELS: Record<FilterCategory, string> = {
  submissions: "filterSubmissions",
  policies: "filterPolicies",
  votes: "filterVotes",
  disputes: "filterDisputes",
  users: "filterUsers",
  system: "filterSystem",
};

export default function EvidencePage() {
  const t = useTranslations("analytics");
  const locale = useLocale();
  const searchParams = useSearchParams();
  const entityFilter = searchParams.get("entity");

  const [entries, setEntries] = useState<EvidenceEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [chainStatus, setChainStatus] = useState<"unknown" | "valid" | "invalid" | "verifying">("unknown");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [page, setPage] = useState(1);
  const [showAll, setShowAll] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Set<FilterCategory>>(new Set());
  const perPage = 50;

  useEffect(() => {
    let url = `/analytics/evidence?page=${page}&per_page=${perPage}`;
    if (entityFilter) url += `&entity_id=${entityFilter}`;
    apiGet<EvidenceResponse>(url)
      .then((data) => {
        setEntries(data.entries);
        setTotal(data.total);
      })
      .catch(() => {
        setEntries([]);
        setTotal(0);
      });
  }, [page, entityFilter]);

  const runVerify = useCallback(async () => {
    setChainStatus("verifying");
    try {
      const result = await apiGet<{valid: boolean; entries_checked: number}>("/analytics/evidence/verify");
      setChainStatus(result.valid ? "valid" : "invalid");
    } catch {
      setChainStatus("invalid");
    }
  }, []);

  const visibleEntries = entries.filter((e) => {
    if (activeFilters.size > 0) {
      const matchesFilter = Array.from(activeFilters).some((cat) =>
        EVENT_CATEGORIES[cat].includes(e.event_type),
      );
      if (!matchesFilter) return false;
    } else if (!showAll && !isDeliberationEvent(e.event_type)) {
      return false;
    }
    if (search) {
      return (
        e.entity_id.includes(search) ||
        e.event_type.includes(search) ||
        e.hash.includes(search) ||
        eventDescription(e, t).toLowerCase().includes(search.toLowerCase())
      );
    }
    return true;
  });

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const copyHash = async (hash: string) => {
    await navigator.clipboard.writeText(hash);
  };

  const toggleFilter = (cat: FilterCategory) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const payloadDisplayKeys = (entry: EvidenceEntry): [string, string][] => {
    const p = entry.payload;
    const pairs: [string, string][] = [];
    if (p.policy_topic) pairs.push(["Topic", String(p.policy_topic)]);
    if (p.confidence != null) pairs.push(["Confidence", `${Math.round(Number(p.confidence) * 100)}%`]);
    if (p.status) pairs.push(["Status", String(p.status)]);
    if (p.language) pairs.push(["Language", String(p.language)]);
    if (p.model_version) pairs.push(["Model", String(p.model_version)]);
    if (p.escalated != null) pairs.push(["Escalated", String(p.escalated)]);
    if (p.total_voters != null) pairs.push(["Total voters", String(p.total_voters)]);
    if (p.member_count != null) pairs.push(["Members", String(p.member_count)]);
    if (p.cycle_duration_hours != null) pairs.push(["Duration", `${p.cycle_duration_hours}h`]);
    if (p.resolution_seconds != null)
      pairs.push(["Resolution time", `${Math.round(Number(p.resolution_seconds))}s`]);
    return pairs;
  };

  return (
    <PageShell
      title={t("evidence")}
      actions={
        <div className="flex items-center gap-3">
          <ChainStatusBadge status={chainStatus} />
          <button
            onClick={runVerify}
            disabled={chainStatus === "verifying"}
            type="button"
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            {t("verifyChain")}
          </button>
        </div>
      }
    >
      {/* Filters */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setShowAll(!showAll);
              setActiveFilters(new Set());
            }}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              !showAll && activeFilters.size === 0
                ? "bg-accent text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
            }`}
          >
            {showAll ? t("showDeliberation") : activeFilters.size === 0 ? t("showAll") : t("showAll")}
          </button>
          {(Object.keys(EVENT_CATEGORIES) as FilterCategory[]).map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => toggleFilter(cat)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                activeFilters.has(cat)
                  ? "bg-accent text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
              }`}
            >
              {t(FILTER_LABELS[cat])}
            </button>
          ))}
        </div>

        {/* Search + count */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative">
            <svg
              className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
            <input
              type="text"
              placeholder={t("search")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label={t("search")}
              className="w-full rounded-lg border border-gray-300 bg-white py-2 pe-4 ps-10 text-sm outline-none transition-colors placeholder:text-gray-400 focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-slate-600 dark:bg-slate-800 dark:placeholder:text-slate-500 sm:w-80"
            />
          </div>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            {t("totalEntries")}: <span className="font-semibold">{total}</span>
          </p>
        </div>
      </div>

      {entityFilter && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 px-4 py-2 text-sm text-blue-700 dark:bg-blue-900/20 dark:text-blue-300">
          <span>Filtered by entity: <code className="font-mono text-xs">{entityFilter}</code></span>
          <Link
            href={`/${locale}/collective-concerns/evidence`}
            className="ms-2 text-xs underline hover:no-underline"
          >
            Clear filter
          </Link>
        </div>
      )}

      {/* Evidence list */}
      <div className="space-y-2">
        {visibleEntries.map((entry) => (
          <Card key={entry.id} className="p-0">
            <button
              type="button"
              onClick={() => toggleExpand(entry.id)}
              onKeyDown={(e) => e.key === "Enter" && toggleExpand(entry.id)}
              className="flex w-full items-center justify-between px-5 py-4 text-start transition-colors hover:bg-gray-50 dark:hover:bg-slate-700/50"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="inline-flex shrink-0 items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                    {entry.event_type.replace(/_/g, " ")}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-slate-400">
                    {entry.entity_type}
                  </span>
                </div>
                <p className="mt-1 text-sm text-gray-700 dark:text-slate-200">
                  {eventDescription(entry, t)}
                </p>
              </div>
              <div className="ms-4 flex shrink-0 items-center gap-2">
                <span className="text-xs text-gray-400 dark:text-slate-500">
                  {relativeTime(entry.timestamp)}
                </span>
                <svg
                  className={`h-4 w-4 text-gray-400 transition-transform ${expanded.has(entry.id) ? "rotate-180" : ""}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="m19 9-7 7-7-7" />
                </svg>
              </div>
            </button>

            {expanded.has(entry.id) && (
              <div className="border-t border-gray-200 bg-gray-50 px-5 py-4 dark:border-slate-700 dark:bg-slate-800/50">
                <div className="space-y-3">
                  {/* Key-value payload fields */}
                  {payloadDisplayKeys(entry).length > 0 && (
                    <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
                      {payloadDisplayKeys(entry).map((pair) => (
                        <div key={pair[0]}>
                          <span className="font-medium text-gray-500 dark:text-slate-400">{pair[0]}:</span>{" "}
                          <span className="text-gray-700 dark:text-slate-200">{pair[1]}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Raw text if available */}
                  {entry.payload.raw_text ? (
                    <div>
                      <span className="mb-1 block text-xs font-medium text-gray-500 dark:text-slate-400">
                        Original text:
                      </span>
                      <p className="rounded-md bg-white p-3 text-sm dark:bg-slate-900">
                        {String(entry.payload.raw_text)}
                      </p>
                    </div>
                  ) : null}

                  {/* Full payload JSON */}
                  <details className="text-xs">
                    <summary className="cursor-pointer font-medium text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200">
                      Full payload
                    </summary>
                    <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-white p-3 font-mono text-xs dark:bg-slate-900">
                      {JSON.stringify(entry.payload, null, 2)}
                    </pre>
                  </details>

                  {/* Hash chain footer */}
                  <div className="space-y-1 border-t border-gray-200 pt-3 text-xs dark:border-slate-700">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-500 dark:text-slate-400">Hash:</span>
                      <code className="flex-1 truncate font-mono">{entry.hash}</code>
                      <button
                        type="button"
                        onClick={() => copyHash(entry.hash)}
                        className="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                        aria-label="Copy hash"
                      >
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" />
                        </svg>
                      </button>
                    </div>
                    <div>
                      <span className="font-medium text-gray-500 dark:text-slate-400">Prev:</span>{" "}
                      <code className="font-mono">{entry.prev_hash}</code>
                    </div>
                    <div>
                      <span className="font-medium text-gray-500 dark:text-slate-400">Entity:</span>{" "}
                      <code className="font-mono">{entry.entity_id}</code>
                    </div>
                    <div>
                      <span className="font-medium text-gray-500 dark:text-slate-400">Time:</span>{" "}
                      <span>{entry.timestamp}</span>
                    </div>
                  </div>

                  {/* Analytics link */}
                  {entityLink(entry, locale) && (
                    <Link
                      href={entityLink(entry, locale)!}
                      className="inline-flex items-center gap-1 rounded-lg bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20"
                    >
                      {t("viewInAnalytics")}
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                      </svg>
                    </Link>
                  )}
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-center gap-2">
        <button
          onClick={() => setPage(Math.max(1, page - 1))}
          disabled={page <= 1}
          type="button"
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          ← Previous
        </button>
        <span className="rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium dark:bg-slate-700">
          {page}
        </span>
        <button
          onClick={() => setPage(page + 1)}
          disabled={page * perPage >= total}
          type="button"
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          Next →
        </button>
      </div>
    </PageShell>
  );
}
