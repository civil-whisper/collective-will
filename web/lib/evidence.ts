export type EvidenceEntry = {
  id: number;
  timestamp: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  hash: string;
  prev_hash: string;
};

export type EvidenceResponse = {
  total: number;
  page: number;
  per_page: number;
  entries: EvidenceEntry[];
};

async function sha256Hex(value: string): Promise<string> {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Matches Python's json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).
 * Recursively sorts object keys at every nesting level.
 */
export function canonicalJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "number" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  const parts = keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(obj[k]));
  return "{" + parts.join(",") + "}";
}

export async function verifyChain(entries: EvidenceEntry[]): Promise<{valid: boolean; failedIndex?: number}> {
  let previous = "genesis";
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const material = {
      timestamp: entry.timestamp,
      event_type: entry.event_type,
      entity_type: entry.entity_type,
      entity_id: entry.entity_id.toLowerCase(),
      payload: entry.payload,
      prev_hash: entry.prev_hash
    };
    const serialized = canonicalJson(material);
    const expected = await sha256Hex(serialized);
    if (entry.hash !== expected || entry.prev_hash !== previous) {
      return {valid: false, failedIndex: index};
    }
    previous = entry.hash;
  }
  return {valid: true};
}

const DELIBERATION_EVENT_TYPES = new Set([
  "submission_received",
  "submission_rejected_not_policy",
  "candidate_created",
  "cluster_created",
  "cluster_updated",
  "cluster_merged",
  "ballot_question_generated",
  "policy_options_generated",
  "vote_cast",
  "policy_endorsed",
  "cycle_opened",
  "cycle_closed",
  "dispute_escalated",
  "dispute_resolved",
]);

export function isDeliberationEvent(eventType: string): boolean {
  return DELIBERATION_EVENT_TYPES.has(eventType);
}

export type FilterCategory = "submissions" | "policies" | "votes" | "disputes" | "users" | "system";

export const EVENT_CATEGORIES: Record<FilterCategory, string[]> = {
  submissions: ["submission_received", "submission_rejected_not_policy"],
  policies: ["candidate_created", "cluster_created", "cluster_updated", "cluster_merged", "ballot_question_generated", "policy_options_generated"],
  votes: ["vote_cast", "policy_endorsed", "cycle_opened", "cycle_closed"],
  disputes: ["dispute_escalated", "dispute_resolved"],
  users: ["user_verified"],
  system: ["anchor_computed", "dispute_metrics_recorded", "dispute_tuning_recommended"],
};

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "...";
}

function str(v: unknown): string {
  return typeof v === "string" ? v : String(v ?? "");
}

export function eventDescription(
  entry: EvidenceEntry,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  const p = entry.payload;
  switch (entry.event_type) {
    case "submission_received": {
      if (p.status === "rejected_high_risk_pii") return t("events.submissionRejectedPii");
      const text = str(p.raw_text);
      return text
        ? t("events.submissionReceived", {text: truncate(text, 80)})
        : t("events.submissionReceivedGeneric");
    }
    case "submission_rejected_not_policy":
      return t("events.submissionRejectedNotPolicy");
    case "candidate_created":
      return t("events.candidateCreated", {
        title: truncate(str(p.title), 60),
        topic: str(p.policy_topic),
        confidence: String(Math.round(Number(p.confidence ?? 0) * 100)),
      });
    case "cluster_created":
      return t("events.clusterCreated", {
        summary: truncate(str(p.summary ?? p.policy_key ?? ""), 60),
        memberCount: String(p.member_count ?? "?"),
      });
    case "cluster_updated":
      return t("events.clusterUpdated", {
        summary: truncate(str(p.summary ?? p.policy_key ?? ""), 60),
        memberCount: String(p.new_member_count ?? p.member_count ?? "?"),
      });
    case "cluster_merged":
      return t("events.clusterMerged", {
        mergedKey: str(p.merged_key),
        survivorKey: str(p.survivor_key),
      });
    case "ballot_question_generated":
      return t("events.ballotQuestionGenerated", {
        policyKey: str(p.policy_key),
      });
    case "policy_options_generated":
      return t("events.policyOptionsGenerated", {
        optionCount: String(p.option_count ?? "?"),
      });
    case "vote_cast":
      return t("events.voteCast", {
        count: String((p.approved_cluster_ids as unknown[])?.length ?? 0),
      });
    case "policy_endorsed":
      return t("events.policyEndorsed");
    case "cycle_opened":
      return t("events.cycleOpened", {
        count: String((p.cluster_ids as unknown[])?.length ?? 0),
      });
    case "cycle_closed":
      return t("events.cycleClosed", {
        totalVoters: String(p.total_voters ?? 0),
      });
    case "dispute_escalated":
      return t("events.disputeEscalated");
    case "dispute_resolved":
      return p.resolved_title
        ? t("events.disputeResolved", {title: truncate(str(p.resolved_title), 60)})
        : t("events.disputeResolvedGeneric");
    case "user_verified":
      return t("events.userVerified", {method: str(p.method)});
    case "anchor_computed":
      return t("events.anchorComputed", {
        entryCount: String(p.entry_count ?? 0),
      });
    case "dispute_metrics_recorded":
      return t("events.disputeMetrics");
    case "dispute_tuning_recommended":
      return t("events.disputeTuning");
    default:
      return entry.event_type;
  }
}

export function entityLink(entry: EvidenceEntry, locale: string): string | null {
  switch (entry.entity_type) {
    case "cluster":
      return `/${locale}/collective-concerns/clusters/${entry.entity_id}`;
    case "voting_cycle":
      return `/${locale}/collective-concerns/top-policies`;
    case "vote":
      return `/${locale}/collective-concerns/top-policies`;
    default:
      return null;
  }
}

export function relativeTime(isoTimestamp: string): string {
  const now = Date.now();
  const then = new Date(isoTimestamp).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}
