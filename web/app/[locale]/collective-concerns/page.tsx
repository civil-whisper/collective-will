import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";
import {MetricCard, PageShell, TopicBadge} from "@/components/ui";

function formatCycleEnd(endsAt: string, locale: string): string {
  const end = new Date(endsAt);
  const now = new Date();
  const hoursLeft = Math.max(0, (end.getTime() - now.getTime()) / 3_600_000);
  const dateStr = end.toLocaleDateString(locale === "fa" ? "fa-IR" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  if (hoursLeft < 1) return dateStr;
  if (hoursLeft < 24) return `${dateStr} (~${Math.round(hoursLeft)}h left)`;
  const days = Math.floor(hoursLeft / 24);
  const hrs = Math.round(hoursLeft % 24);
  return `${dateStr} (~${days}d ${hrs}h left)`;
}

type Cluster = {
  id: string;
  policy_topic: string;
  policy_key: string;
  status: string;
  summary: string;
  member_count: number;
  approval_count: number;
  endorsement_count: number;
};

type ActiveCycle = {
  id: string;
  started_at: string;
  ends_at: string;
  cluster_count: number;
};

type CycleStats = {
  total_voters: number;
  total_submissions: number;
  pending_submissions: number;
  current_cycle: string | null;
  active_cycle: ActiveCycle | null;
};

type UnclusteredItem = {
  id: string;
  title: string;
  summary: string;
  policy_topic: string;
  policy_key: string;
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
      active_cycle: null,
    })),
    apiGet<UnclusteredResponse>("/analytics/unclustered").catch(() => ({
      total: 0,
      items: [],
    })),
  ]);

  const bySupport = (a: Cluster, b: Cluster) =>
    (b.endorsement_count + b.member_count) -
    (a.endorsement_count + a.member_count);

  const openConcerns = clusters.filter((c) => c.status === "open").sort(bySupport);
  const archivedConcerns = clusters.filter((c) => c.status === "archived").sort(bySupport);

  return (
    <PageShell title={t("pageTitle")}>
      <p className="text-sm text-gray-600 dark:text-slate-400">
        {t("pageDescription")}
      </p>

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

      {stats.active_cycle && (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 dark:border-emerald-700 dark:bg-emerald-950/40">
          <p className="font-semibold text-emerald-900 dark:text-emerald-200">
            🗳️ {t("activeCycleBanner", {count: stats.active_cycle.cluster_count})}
          </p>
          <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-300">
            {t("activeCycleEnds", {endsAt: formatCycleEnd(stats.active_cycle.ends_at, locale)})}
          </p>
        </div>
      )}

      {stats.pending_submissions > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          {t("pendingSubmissions", {count: stats.pending_submissions})}
        </div>
      )}

      <div>
        <h2 className="mb-3 text-lg font-semibold">{t("activeConcerns")}</h2>
        {openConcerns.length === 0 ? (
          <div className="rounded-lg border border-gray-200 bg-white p-12 text-center dark:border-slate-700 dark:bg-slate-800">
            <p className="text-gray-500 dark:text-slate-400">{t("noClusters")}</p>
          </div>
        ) : (
          <ConcernList concerns={openConcerns} locale={locale} t={t} />
        )}
      </div>

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
                id={`candidate-${item.id}`}
                className="scroll-mt-24 rounded-lg border border-gray-200 bg-white px-5 py-4 transition-shadow target:ring-2 target:ring-accent target:shadow-lg dark:border-slate-700 dark:bg-slate-800"
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
                      <TopicBadge topic={item.policy_topic} />
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

      {archivedConcerns.length > 0 && (
        <div>
          <h2 className="mb-1 text-lg font-semibold">{t("archivedConcerns")}</h2>
          <p className="mb-3 text-sm text-gray-500 dark:text-slate-400">
            {t("archivedConcernsDescription")}
          </p>
          <ConcernList concerns={archivedConcerns} locale={locale} t={t} />
        </div>
      )}

      {/* Footer links */}
      <div className="flex items-center gap-4 text-sm">
        <Link
          href={`/${locale}/collective-concerns/top-policies`}
          className="font-medium text-accent hover:underline"
        >
          {t("topPolicies")} →
        </Link>
        <Link
          href={`/${locale}/collective-concerns/evidence`}
          className="font-medium text-accent hover:underline"
        >
          {t("evidence")} →
        </Link>
      </div>
    </PageShell>
  );
}

function ConcernList({
  concerns,
  locale,
  t,
}: {
  concerns: Cluster[];
  locale: string;
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  return (
    <div className="space-y-2">
      {concerns.map((concern) => (
        <Link
          key={concern.id}
          href={`/${locale}/collective-concerns/clusters/${concern.id}`}
          className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-5 py-4 transition-colors hover:bg-gray-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
        >
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{concern.summary}</p>
            <div className="mt-1 flex items-center gap-3">
              <TopicBadge topic={concern.policy_topic} />
              {concern.status === "archived" && (
                <span className="rounded bg-gray-200 px-1.5 py-0.5 text-xs font-medium text-gray-600 dark:bg-slate-600 dark:text-slate-300">
                  {t("archived")}
                </span>
              )}
              <span className="text-xs text-gray-500 dark:text-slate-400">
                {t("submissions")}: {concern.member_count}
              </span>
              <span className="text-xs text-gray-500 dark:text-slate-400">
                {t("endorsements")}: {concern.endorsement_count}
              </span>
            </div>
          </div>
          <div className="ms-4 text-end">
            <p className="text-lg font-bold">
              {concern.endorsement_count + concern.member_count}
            </p>
            <p className="text-xs text-gray-500 dark:text-slate-400">
              {t("totalSupport")}
            </p>
          </div>
        </Link>
      ))}
    </div>
  );
}
