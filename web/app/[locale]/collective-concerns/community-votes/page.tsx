import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";
import {PageShell, MetricCard, TopicBadge, Card} from "@/components/ui";

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

type RankedPolicy = {
  cluster_id: string;
  summary?: string;
  policy_topic?: string;
  approval_count: number;
  approval_rate: number;
};

export default async function CommunityVotesPage() {
  const t = await getTranslations("analytics");
  const locale = await getLocale();

  const [ranked, stats] = await Promise.all([
    apiGet<RankedPolicy[]>("/analytics/top-policies").catch(() => []),
    apiGet<CycleStats>("/analytics/stats").catch(() => ({
      total_voters: 0,
      total_submissions: 0,
      pending_submissions: 0,
      current_cycle: null,
      active_cycle: null,
    })),
  ]);

  const hasActiveCycle = stats.active_cycle !== null;
  const hasResults = ranked.length > 0;

  return (
    <PageShell title={t("communityVotes")}>
      <p className="text-sm text-gray-600 dark:text-slate-400">
        {t("communityVotesDescription")}
      </p>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <MetricCard
          label={t("totalVoters")}
          value={stats.total_voters.toLocaleString()}
        />
        <MetricCard
          label={t("activeVotes")}
          value={hasActiveCycle && stats.active_cycle ? stats.active_cycle.cluster_count.toLocaleString() : "0"}
        />
        <MetricCard
          label={t("archivedVotes")}
          value={ranked.length.toLocaleString()}
        />
      </div>

      {hasActiveCycle && stats.active_cycle && (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-5 dark:border-emerald-700 dark:bg-emerald-950/40">
          <p className="font-semibold text-emerald-900 dark:text-emerald-200">
            🗳️ {t("activeCycleBanner", {count: stats.active_cycle.cluster_count})}
          </p>
          <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-300">
            {t("activeCycleEnds", {endsAt: formatCycleEnd(stats.active_cycle.ends_at, locale)})}
          </p>
        </div>
      )}

      {!hasActiveCycle && !hasResults && (
        <Card>
          <p className="py-8 text-center text-gray-500 dark:text-slate-400">
            {t("noVotesYet")}
          </p>
        </Card>
      )}

      {hasResults && (
        <div>
          <h2 className="mb-3 text-lg font-semibold">
            {t("votingResults")}
          </h2>
          <div className="space-y-2">
            {ranked.map((item, index) => {
              const pct = Math.round(item.approval_rate * 100);
              return (
                <div
                  key={item.cluster_id}
                  className="group relative overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-800"
                >
                  <div
                    className="absolute inset-y-0 start-0 bg-accent/5 transition-all dark:bg-accent/10"
                    style={{width: `${pct}%`}}
                  />
                  <div className="relative flex items-center gap-4 px-5 py-4">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 text-sm font-bold text-gray-600 dark:bg-slate-700 dark:text-slate-300">
                      {index + 1}
                    </span>

                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/${locale}/collective-concerns/clusters/${item.cluster_id}`}
                        className="block truncate font-medium text-gray-900 hover:text-accent dark:text-slate-100 dark:hover:text-indigo-300"
                      >
                        {item.summary ?? item.cluster_id}
                      </Link>
                      {item.policy_topic && (
                        <div className="mt-1">
                          <TopicBadge topic={item.policy_topic} />
                        </div>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-6 text-end">
                      <div>
                        <p className="text-lg font-bold">{pct}%</p>
                        <p className="text-xs text-gray-500 dark:text-slate-400">
                          {t("approvalRate")}
                        </p>
                      </div>
                      <div>
                        <p className="text-lg font-bold">{item.approval_count.toLocaleString()}</p>
                        <p className="text-xs text-gray-500 dark:text-slate-400">
                          {t("approvalCount")}
                        </p>
                      </div>
                      <Link
                        href={`/${locale}/collective-concerns/evidence?entity=${item.cluster_id}`}
                        className="rounded p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-accent dark:hover:bg-slate-700"
                        title={t("viewAuditTrail")}
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 0 0 2.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 0 0-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75 2.25 2.25 0 0 0-.1-.664m-5.8 0A2.251 2.251 0 0 1 13.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25Z" />
                        </svg>
                      </Link>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </PageShell>
  );
}
