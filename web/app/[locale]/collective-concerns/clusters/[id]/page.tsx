import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";
import {PageShell, MetricCard, DomainBadge, Card, StatusBadge} from "@/components/ui";

type PolicyCandidatePublic = {
  id: string;
  title: string;
  summary: string;
  domain: string;
  confidence: number;
};

type ClusterDetail = {
  id: string;
  summary: string;
  summary_en?: string;
  domain: string;
  member_count: number;
  approval_count: number;
  variance_flag: boolean;
  candidates: PolicyCandidatePublic[];
  grouping_rationale?: string;
};

type Props = {
  params: Promise<{id: string}>;
};

export default async function ClusterDetailPage({params}: Props) {
  const {id} = await params;
  const t = await getTranslations("analytics");
  const locale = await getLocale();
  const cluster = await apiGet<ClusterDetail>(`/analytics/clusters/${id}`).catch(() => null);

  if (!cluster) {
    return (
      <PageShell title={t("clusters")}>
        <Card>
          <p className="py-8 text-center text-gray-500 dark:text-slate-400">
            {t("noClusters")}
          </p>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell
      title={cluster.summary}
      subtitle={cluster.summary_en ?? undefined}
      actions={
        <div className="flex items-center gap-2">
          <DomainBadge domain={cluster.domain} />
          {cluster.variance_flag && (
            <StatusBadge label={t("varianceFlag")} variant="warning" />
          )}
        </div>
      }
    >
      {/* Metrics */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard label={t("memberCount")} value={cluster.member_count.toLocaleString()} />
        <MetricCard label={t("approvalCount")} value={cluster.approval_count.toLocaleString()} />
        <MetricCard label={t("domain")} value={cluster.domain.replace(/_/g, " ")} />
        <Link
          href={`/${locale}/collective-concerns/evidence?entity=${id}`}
          className="flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-accent transition-colors hover:bg-accent/5 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25Z" />
          </svg>
          {t("viewAuditTrail")}
        </Link>
      </div>

      {/* Grouping rationale */}
      {cluster.grouping_rationale && (
        <Card className="border-accent/20 bg-accent/5 dark:bg-accent/10">
          <p className="text-sm italic text-gray-700 dark:text-slate-300">
            {cluster.grouping_rationale}
          </p>
        </Card>
      )}

      {/* Candidates / member submissions */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">{t("memberCount")}</h2>
        <div className="space-y-3">
          {cluster.candidates.map((candidate) => (
            <Card key={candidate.id}>
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{candidate.title}</p>
                  <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">
                    {candidate.summary}
                  </p>
                  <div className="mt-2">
                    <DomainBadge domain={candidate.domain} />
                  </div>
                </div>
                <div className="text-end">
                  <div className="text-sm font-medium">
                    {Math.round(candidate.confidence * 100)}%
                  </div>
                  <div className="text-xs text-gray-500 dark:text-slate-400">
                    confidence
                  </div>
                </div>
              </div>
              {/* Confidence bar */}
              <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-slate-700">
                <div
                  className="h-full rounded-full bg-accent transition-all"
                  style={{width: `${Math.round(candidate.confidence * 100)}%`}}
                />
              </div>
            </Card>
          ))}
        </div>
      </div>
    </PageShell>
  );
}
