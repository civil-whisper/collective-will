import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";
import {redirect} from "next/navigation";

import {DisputeButton} from "@/components/DisputeButton";
import {DisputeStatus} from "@/components/DisputeStatus";
import {apiGet} from "@/lib/api";
import {buildBearerHeaders, getBackendAccessToken} from "@/lib/backend-auth";
import {eventDescription} from "@/lib/evidence";
import {
  type ReceiptEntry,
  type ReceiptListResponse,
  type ReceiptStatus,
  type ReceiptVerification,
  formatReceiptTimestamp,
  reachedReceiptStates,
  receiptBadgeVariant,
} from "@/lib/receipts";
import {PageShell, MetricCard, Card, TopicBadge, StatusBadge} from "@/components/ui";

type Submission = {
  id: string;
  raw_text: string;
  status: string;
  hash: string;
  candidate?: {
    title: string;
    summary: string;
    policy_topic: string;
    confidence: number;
  };
  cluster?: {
    id: string;
    summary: string;
    approval_count: number;
  };
  dispute_status?: "open" | "resolved" | null;
};

type Vote = {
  id: string;
  cycle_id: string;
  approved_cluster_ids?: string[];
};

type ReceiptWithVerification = {
  entry: ReceiptEntry;
  verification: ReceiptVerification;
};

async function getSubmissions(accessToken: string): Promise<Submission[]> {
  return apiGet<Submission[]>("/user/dashboard/submissions", {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => []);
}

async function getVotes(accessToken: string): Promise<Vote[]> {
  return apiGet<Vote[]>("/user/dashboard/votes", {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => []);
}

async function getReceipts(accessToken: string): Promise<ReceiptEntry[]> {
  const response = await apiGet<ReceiptListResponse>("/user/dashboard/receipts", {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => null);
  return response?.entries ?? [];
}

async function getReceiptVerification(accessToken: string, entryHash: string): Promise<ReceiptVerification> {
  return apiGet<ReceiptVerification>(`/user/dashboard/receipts/${entryHash}/verify`, {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => ({
    status: "recorded",
    receipt_valid: true,
    entry_found: true,
    bundle_day: "",
    included_in_public_bundle: false,
    bundle_hash_matches_manifest: false,
    ots_proof_present: false,
    ots_verified: false,
    verified_before: null,
    download_urls: {
      bundle: null,
      manifest: null,
      ots_proof: null,
    },
  }));
}

const STATUS_VARIANT: Record<string, "success" | "warning" | "info" | "neutral"> = {
  processed: "success",
  pending: "info",
  flagged: "warning",
  rejected: "error" as "warning",
};

export async function generateMetadata() {
  const t = await getTranslations("dashboard");
  return { title: t("title") };
}

export default async function DashboardPage() {
  const accessToken = await getBackendAccessToken();
  const t = await getTranslations("dashboard");
  const tAnalytics = await getTranslations("analytics");
  const tReceipt = await getTranslations("receiptVerification");
  const locale = await getLocale();
  if (!accessToken) {
    redirect(`/${locale}/sign-in`);
  }
  const [submissions, votes, receipts] = await Promise.all([
    getSubmissions(accessToken),
    getVotes(accessToken),
    getReceipts(accessToken),
  ]);
  const receiptsWithVerification: ReceiptWithVerification[] = await Promise.all(
    receipts.map(async (entry) => ({
      entry,
      verification: await getReceiptVerification(accessToken, entry.hash),
    })),
  );

  return (
    <PageShell title={t("title")}>
      {/* Overview metrics */}
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard label={t("totalSubmissions")} value={submissions.length} />
        <MetricCard label={t("totalVotes")} value={votes.length} />
        <MetricCard label={t("totalReceipts")} value={receiptsWithVerification.length} />
      </div>

      {/* Submissions */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">{t("submissions")}</h2>
        {submissions.length === 0 ? (
          <Card>
            <p className="py-4 text-center text-sm text-gray-500 dark:text-slate-400">
              {t("noSubmissions")}
            </p>
          </Card>
        ) : (
          <div className="space-y-3">
            {submissions.map((sub) => (
              <Card key={sub.id}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{sub.raw_text}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <StatusBadge
                        label={sub.status === "pending" ? t("processing") : sub.status}
                        variant={STATUS_VARIANT[sub.status] ?? "neutral"}
                      />
                    </div>
                  </div>
                </div>

                {sub.candidate && (
                  <div className="mt-3 rounded-md bg-gray-50 p-3 dark:bg-slate-700/50">
                    <p className="text-sm font-medium">→ {sub.candidate.title}</p>
                    <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
                      {sub.candidate.summary}
                    </p>
                    <div className="mt-2 flex items-center gap-2">
                      <TopicBadge topic={sub.candidate.policy_topic} />
                      <span className="text-xs text-gray-500 dark:text-slate-400">
                        {Math.round(sub.candidate.confidence * 100)}% confidence
                      </span>
                    </div>
                  </div>
                )}

                {sub.cluster && (
                  <div className="mt-3">
                    <Link
                      href={`/${locale}/collective-concerns/clusters/${sub.cluster.id}`}
                      className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
                    >
                      {sub.cluster.summary}
                      <span className="text-xs text-gray-500 dark:text-slate-400">
                        ({sub.cluster.approval_count} approvals)
                      </span>
                    </Link>
                  </div>
                )}

                <div className="mt-3 border-t border-gray-200 pt-3 dark:border-slate-700">
                  {sub.dispute_status ? (
                    <DisputeStatus status={sub.dispute_status === "open" ? "open" : "resolved"} />
                  ) : (
                    sub.status === "processed" && <DisputeButton submissionId={sub.id} />
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Votes */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">{t("votes")}</h2>
        {votes.length === 0 ? (
          <Card>
            <p className="py-4 text-center text-sm text-gray-500 dark:text-slate-400">
              {t("noVotes")}
            </p>
          </Card>
        ) : (
          <div className="space-y-2">
            {votes.map((vote) => (
              <Card key={vote.id}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">
                    Cycle: <code className="font-mono text-xs">{vote.cycle_id}</code>
                  </span>
                  {vote.approved_cluster_ids && (
                    <span className="text-xs text-gray-500 dark:text-slate-400">
                      {vote.approved_cluster_ids.length} clusters approved
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Receipts */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">{t("receipts")}</h2>
        {receiptsWithVerification.length === 0 ? (
          <Card>
            <p className="py-4 text-center text-sm text-gray-500 dark:text-slate-400">
              {t("noReceipts")}
            </p>
          </Card>
        ) : (
          <div className="space-y-3">
            {receiptsWithVerification.map(({entry, verification}) => {
              const reachedStates = new Set<ReceiptStatus>(reachedReceiptStates(verification.status));
              return (
                <Card key={entry.hash}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{eventDescription(entry, tAnalytics)}</p>
                      <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
                        {formatReceiptTimestamp(entry.timestamp, locale)}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(["recorded", "published", "timestamped"] as ReceiptStatus[]).map((status) => (
                          <StatusBadge
                            key={status}
                            label={tReceipt(`states.${status}.label`)}
                            variant={reachedStates.has(status) ? receiptBadgeVariant(status) : "neutral"}
                          />
                        ))}
                        {verification.status === "verified" && (
                          <StatusBadge
                            label={tReceipt("states.verified.label")}
                            variant={receiptBadgeVariant("verified")}
                          />
                        )}
                        {verification.status === "failed" && (
                          <StatusBadge
                            label={tReceipt("states.failed.label")}
                            variant={receiptBadgeVariant("failed")}
                          />
                        )}
                      </div>
                    </div>
                    <Link
                      href={`/${locale}/my-activity/receipts/${entry.hash}`}
                      className="inline-flex items-center justify-center rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90"
                    >
                      {tReceipt("verifyReceipt")}
                    </Link>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </PageShell>
  );
}
