"use client";

import {useState, useEffect, useCallback} from "react";
import {useTranslations} from "next-intl";

import {apiGet} from "@/lib/api";
import {type EvidenceEntry, verifyChain} from "@/lib/evidence";
import {PageShell, ChainStatusBadge, Card} from "@/components/ui";

export default function EvidencePage() {
  const t = useTranslations("analytics");
  const [entries, setEntries] = useState<EvidenceEntry[]>([]);
  const [search, setSearch] = useState("");
  const [chainStatus, setChainStatus] = useState<"unknown" | "valid" | "invalid" | "verifying">("unknown");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const perPage = 50;

  useEffect(() => {
    apiGet<EvidenceEntry[]>(`/analytics/evidence?page=${page}&per_page=${perPage}`)
      .then(setEntries)
      .catch(() => setEntries([]));
  }, [page]);

  const runVerify = useCallback(async () => {
    setChainStatus("verifying");
    const result = await verifyChain(entries);
    setChainStatus(result.valid ? "valid" : "invalid");
  }, [entries]);

  const filtered = search
    ? entries.filter(
        (e) =>
          e.entity_id.includes(search) ||
          e.event_type.includes(search) ||
          e.hash.includes(search),
      )
    : entries;

  const toggleExpand = (hash: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(hash)) {
        next.delete(hash);
      } else {
        next.add(hash);
      }
      return next;
    });
  };

  const copyHash = async (hash: string) => {
    await navigator.clipboard.writeText(hash);
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
          {t("totalEntries")}: <span className="font-semibold">{entries.length}</span>
        </p>
      </div>

      {/* Evidence list */}
      <div className="space-y-2">
        {filtered.map((entry) => (
          <Card key={entry.hash} className="p-0">
            <button
              type="button"
              onClick={() => toggleExpand(entry.hash)}
              onKeyDown={(e) => e.key === "Enter" && toggleExpand(entry.hash)}
              className="flex w-full items-center justify-between px-5 py-4 text-start transition-colors hover:bg-gray-50 dark:hover:bg-slate-700/50"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                    {entry.event_type}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-slate-400">
                    {entry.entity_type}
                  </span>
                </div>
                <p className="mt-1 font-mono text-xs text-gray-500 dark:text-slate-400">
                  {entry.hash.slice(0, 20)}…
                </p>
              </div>
              <div className="ms-4 flex items-center gap-2">
                <span className="text-xs text-gray-400 dark:text-slate-500">
                  {entry.timestamp}
                </span>
                <svg
                  className={`h-4 w-4 text-gray-400 transition-transform ${expanded.has(entry.hash) ? "rotate-180" : ""}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="m19 9-7 7-7-7" />
                </svg>
              </div>
            </button>

            {expanded.has(entry.hash) && (
              <div className="border-t border-gray-200 bg-gray-50 px-5 py-4 dark:border-slate-700 dark:bg-slate-800/50">
                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-500 dark:text-slate-400">Hash:</span>
                    <code className="flex-1 truncate font-mono text-xs">{entry.hash}</code>
                    <button
                      type="button"
                      onClick={() => copyHash(entry.hash)}
                      className="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                      aria-label="Copy hash"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" />
                      </svg>
                    </button>
                  </div>
                  <div>
                    <span className="font-medium text-gray-500 dark:text-slate-400">Prev Hash:</span>{" "}
                    <code className="font-mono text-xs">{entry.prev_hash}</code>
                  </div>
                  <div>
                    <span className="font-medium text-gray-500 dark:text-slate-400">Entity ID:</span>{" "}
                    <code className="font-mono text-xs">{entry.entity_id}</code>
                  </div>
                  <div>
                    <span className="mb-1 block font-medium text-gray-500 dark:text-slate-400">Payload:</span>
                    <pre className="max-h-64 overflow-auto rounded-md bg-white p-3 font-mono text-xs dark:bg-slate-900">
                      {JSON.stringify(entry.payload, null, 2)}
                    </pre>
                  </div>
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
          type="button"
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          Next →
        </button>
      </div>
    </PageShell>
  );
}
