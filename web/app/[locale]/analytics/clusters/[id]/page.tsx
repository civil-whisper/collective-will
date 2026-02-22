import {getTranslations} from "next-intl/server";

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
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <MetricCard label={t("memberCount")} value={cluster.member_count.toLocaleString()} />
        <MetricCard label={t("approvalCount")} value={cluster.approval_count.toLocaleString()} />
        <MetricCard label={t("domain")} value={cluster.domain.replace(/_/g, " ")} />
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
