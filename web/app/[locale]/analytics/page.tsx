import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";
import {MetricCard, BreakdownTable, PageShell, DomainBadge} from "@/components/ui";
import type {BreakdownItem} from "@/components/ui";

type Cluster = {
  id: string;
  summary: string;
  domain: string;
  member_count: number;
  approval_count: number;
  variance_flag: boolean;
};

type CycleStats = {
  total_voters: number;
  total_submissions: number;
  pending_submissions: number;
  current_cycle: string | null;
};

type UnclusteredItem = {
  id: string;
  title: string;
  summary: string;
  domain: string;
  confidence: number;
  raw_text: string | null;
  language: string | null;
};

type UnclusteredResponse = {
  total: number;
  items: UnclusteredItem[];
};

export default async function AnalyticsPage() {
  const t = await getTranslations("analytics");
  const locale = await getLocale();

  const [clusters, stats, unclustered] = await Promise.all([
    apiGet<Cluster[]>("/analytics/clusters").catch(() => []),
    apiGet<CycleStats>("/analytics/stats").catch(() => ({
      total_voters: 0,
      total_submissions: 0,
      pending_submissions: 0,
      current_cycle: null,
    })),
    apiGet<UnclusteredResponse>("/analytics/unclustered").catch(() => ({
      total: 0,
      items: [],
    })),
  ]);

  const sortedClusters = [...clusters].sort(
    (a, b) => b.approval_count - a.approval_count,
  );

  const domainCounts: Record<string, number> = {};
  for (const c of clusters) {
    domainCounts[c.domain] = (domainCounts[c.domain] ?? 0) + c.member_count;
  }
  const domainItems: BreakdownItem[] = Object.entries(domainCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([domain, count]) => ({
      key: domain,
      label: <DomainBadge domain={domain} />,
      value: count,
    }));

  const clusterItems: BreakdownItem[] = sortedClusters.slice(0, 10).map((c) => ({
    key: c.id,
    label: (
      <Link
        href={`/${locale}/analytics/clusters/${c.id}`}
        className="text-gray-900 hover:text-accent dark:text-slate-100 dark:hover:text-indigo-300"
      >
        {c.summary}
      </Link>
    ),
    value: c.approval_count,
    displayValue: `${c.approval_count.toLocaleString()} approvals`,
  }));

  return (
    <PageShell title={t("clusters")}>
      {/* Metric cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          label={t("totalVoters")}
          value={stats.total_voters.toLocaleString()}
        />
        <MetricCard
          label={t("clusters")}
          value={clusters.length.toLocaleString()}
        />
        <MetricCard
          label={t("totalSubmissions")}
          value={stats.total_submissions.toLocaleString()}
        />
        <MetricCard
          label={t("unclustered")}
          value={unclustered.total.toLocaleString()}
        />
      </div>

      {stats.pending_submissions > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          {t("pendingSubmissions", {count: stats.pending_submissions})}
        </div>
      )}

      {clusters.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-12 text-center dark:border-slate-700 dark:bg-slate-800">
          <p className="text-gray-500 dark:text-slate-400">{t("noClusters")}</p>
        </div>
      ) : (
        <>
          {/* Breakdown tables — side by side */}
          <div className="grid gap-4 lg:grid-cols-2">
            <BreakdownTable
              title={t("topPolicies")}
              items={clusterItems}
            />
            <BreakdownTable
              title={t("domain")}
              items={domainItems}
            />
          </div>

          {/* Full cluster list */}
          <div className="space-y-2">
            {sortedClusters.map((cluster) => (
              <Link
                key={cluster.id}
                href={`/${locale}/analytics/clusters/${cluster.id}`}
                className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-5 py-4 transition-colors hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{cluster.summary}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <DomainBadge domain={cluster.domain} />
                    <span className="text-xs text-gray-500 dark:text-slate-400">
                      {t("memberCount")}: {cluster.member_count}
                    </span>
                    {cluster.variance_flag && (
                      <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
                        {t("varianceFlag")}
                      </span>
                    )}
                  </div>
                </div>
                <div className="ms-4 text-end">
                  <p className="text-lg font-bold">{cluster.approval_count}</p>
                  <p className="text-xs text-gray-500 dark:text-slate-400">
                    {t("approvalCount")}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}

      <div>
        <h2 className="mb-3 text-lg font-semibold">{t("unclusteredCandidates")}</h2>
        {unclustered.items.length === 0 ? (
          <div className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
            {t("noUnclusteredCandidates")}
          </div>
        ) : (
          <div className="space-y-3">
            {unclustered.items.map((item) => (
              <div
                key={item.id}
                className="rounded-lg border border-gray-200 bg-white px-5 py-4 dark:border-slate-700 dark:bg-slate-800"
              >
                {item.raw_text && (
                  <div className="mb-3">
                    <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-slate-500">
                      {t("userSubmission")}
                    </p>
                    <blockquote
                      className="border-s-2 border-gray-300 ps-3 text-sm text-gray-600 dark:border-slate-600 dark:text-slate-300"
                      dir={item.language === "fa" ? "rtl" : "ltr"}
                    >
                      {item.raw_text}
                    </blockquote>
                  </div>
                )}
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-slate-500">
                      {t("aiInterpretation")}
                    </p>
                    <p className="font-medium">{item.title}</p>
                    <p className="mt-1 text-sm text-gray-600 dark:text-slate-400">{item.summary}</p>
                    <div className="mt-2">
                      <DomainBadge domain={item.domain} />
                    </div>
                  </div>
                  <div className="text-end">
                    <p className="text-xs text-gray-400 dark:text-slate-500">{t("aiConfidence")}</p>
                    <p className="text-sm font-semibold text-gray-600 dark:text-slate-300">
                      {Math.round(item.confidence * 100)}%
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer links */}
      <div className="flex items-center gap-4 text-sm">
        <Link
          href={`/${locale}/analytics/top-policies`}
          className="font-medium text-accent hover:underline"
        >
          {t("topPolicies")} →
        </Link>
        <Link
          href={`/${locale}/analytics/evidence`}
          className="font-medium text-accent hover:underline"
        >
          {t("evidence")} →
        </Link>
      </div>
    </PageShell>
  );
}
