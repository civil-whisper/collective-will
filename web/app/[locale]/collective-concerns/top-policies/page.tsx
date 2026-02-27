import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";
import {PageShell, TopicBadge, Card} from "@/components/ui";

type RankedPolicy = {
  cluster_id: string;
  summary?: string;
  policy_topic?: string;
  approval_count: number;
  approval_rate: number;
};

export default async function TopPoliciesPage() {
  const t = await getTranslations("analytics");
  const locale = await getLocale();
  const ranked = await apiGet<RankedPolicy[]>("/analytics/top-policies").catch(() => []);

  if (ranked.length === 0) {
    return (
      <PageShell title={t("topPolicies")}>
        <Card>
          <p className="py-8 text-center text-gray-500 dark:text-slate-400">
            {t("noCycles")}
          </p>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell title={t("topPolicies")}>
      <div className="space-y-2">
        {ranked.map((item, index) => {
          const pct = Math.round(item.approval_rate * 100);
          return (
            <div
              key={item.cluster_id}
              className="group relative overflow-hidden rounded-lg border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-800"
            >
              {/* Approval rate bar background */}
              <div
                className="absolute inset-y-0 start-0 bg-accent/5 transition-all dark:bg-accent/10"
                style={{width: `${pct}%`}}
              />
              <div className="relative flex items-center gap-4 px-5 py-4">
                {/* Rank */}
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 text-sm font-bold text-gray-600 dark:bg-slate-700 dark:text-slate-300">
                  {index + 1}
                </span>

                {/* Content */}
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

                {/* Stats */}
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
    </PageShell>
  );
}
