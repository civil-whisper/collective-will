import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";
import {redirect} from "next/navigation";

import {DisputeButton} from "@/components/DisputeButton";
import {DisputeStatus} from "@/components/DisputeStatus";
import {apiGet} from "@/lib/api";
import {buildBearerHeaders, getBackendAccessToken} from "@/lib/backend-auth";
import {PageShell, MetricCard, Card, DomainBadge, StatusBadge} from "@/components/ui";

type Submission = {
  id: string;
  raw_text: string;
  status: string;
  hash: string;
  candidate?: {
    title: string;
    summary: string;
    domain: string;
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

const STATUS_VARIANT: Record<string, "success" | "warning" | "info" | "neutral"> = {
  processed: "success",
  pending: "info",
  flagged: "warning",
  rejected: "error" as "warning",
};

export default async function DashboardPage() {
  const accessToken = await getBackendAccessToken();
  const t = await getTranslations("dashboard");
  const locale = await getLocale();
  if (!accessToken) {
    redirect(`/${locale}/sign-in`);
  }
  const [submissions, votes] = await Promise.all([
    getSubmissions(accessToken),
    getVotes(accessToken),
  ]);

  return (
    <PageShell title={t("title")}>
      {/* Overview metrics */}
      <div className="grid grid-cols-2 gap-4">
        <MetricCard label={t("totalSubmissions")} value={submissions.length} />
        <MetricCard label={t("totalVotes")} value={votes.length} />
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
                      <DomainBadge domain={sub.candidate.domain} />
                      <span className="text-xs text-gray-500 dark:text-slate-400">
                        {Math.round(sub.candidate.confidence * 100)}% confidence
                      </span>
                    </div>
                  </div>
                )}

                {sub.cluster && (
                  <div className="mt-3">
                    <Link
                      href={`/${locale}/analytics/clusters/${sub.cluster.id}`}
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
    </PageShell>
  );
}
