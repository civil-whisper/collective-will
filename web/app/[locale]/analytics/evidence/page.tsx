"use client";

import {useState, useEffect} from "react";
import {useTranslations} from "next-intl";

import {apiGet} from "@/lib/api";
import {type EvidenceEntry, verifyChain} from "@/lib/evidence";

export default function EvidencePage() {
  const t = useTranslations("analytics");
  const [entries, setEntries] = useState<EvidenceEntry[]>([]);
  const [search, setSearch] = useState("");
  const [chainStatus, setChainStatus] = useState<"unknown" | "valid" | "invalid">("unknown");
  const [verifying, setVerifying] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const perPage = 50;

  useEffect(() => {
    apiGet<EvidenceEntry[]>(`/analytics/evidence?page=${page}&per_page=${perPage}`)
      .then(setEntries)
      .catch(() => setEntries([]));
  }, [page]);

  const runVerify = async () => {
    setVerifying(true);
    const result = await verifyChain(entries);
    setChainStatus(result.valid ? "valid" : "invalid");
    setVerifying(false);
  };

  const filtered = search
    ? entries.filter(
        (e) =>
          e.entity_id.includes(search) ||
          e.event_type.includes(search) ||
          e.hash.includes(search),
      )
    : entries;

  const toggleExpand = (hash: string) => {
    const next = new Set(expanded);
    if (next.has(hash)) {
      next.delete(hash);
    } else {
      next.add(hash);
    }
    setExpanded(next);
  };

  return (
    <section>
      <h1>{t("evidence")}</h1>

      <div style={{marginBottom: "1rem"}}>
        {chainStatus === "valid" && <span style={{color: "green"}}>✅ {t("chainValid")}</span>}
        {chainStatus === "invalid" && <span style={{color: "red"}}>❌ {t("chainInvalid")}</span>}
        <button onClick={runVerify} disabled={verifying} type="button" style={{marginInlineStart: "1rem"}}>
          {verifying ? "..." : t("verifyChain")}
        </button>
      </div>

      <div style={{marginBottom: "1rem"}}>
        <input
          type="text"
          placeholder={t("search")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label={t("search")}
          style={{padding: "0.5rem", width: "100%", maxWidth: "400px"}}
        />
      </div>

      <p>{t("totalEntries")}: {entries.length}</p>

      <ul style={{listStyle: "none", padding: 0}}>
        {filtered.map((entry) => (
          <li key={entry.hash} style={{marginBottom: "0.5rem", padding: "0.5rem", border: "1px solid #ddd"}}>
            <div
              onClick={() => toggleExpand(entry.hash)}
              style={{cursor: "pointer"}}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && toggleExpand(entry.hash)}
            >
              <strong>{entry.event_type}</strong> — {entry.entity_type} — {entry.timestamp}
              <br />
              Hash: <code>{entry.hash.slice(0, 16)}...</code>
            </div>
            {expanded.has(entry.hash) && (
              <div style={{marginTop: "0.5rem", padding: "0.5rem", background: "#f9f9f9"}}>
                <p>Hash: <code>{entry.hash}</code></p>
                <p>Prev Hash: <code>{entry.prev_hash}</code></p>
                <p>Entity ID: {entry.entity_id}</p>
                <pre style={{overflow: "auto"}}>{JSON.stringify(entry.payload, null, 2)}</pre>
              </div>
            )}
          </li>
        ))}
      </ul>

      <div style={{display: "flex", gap: "1rem", marginTop: "1rem"}}>
        <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} type="button">
          Previous
        </button>
        <span>Page {page}</span>
        <button onClick={() => setPage(page + 1)} type="button">
          Next
        </button>
      </div>
    </section>
  );
}
