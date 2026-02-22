import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";
import {PageShell, DomainBadge, Card} from "@/components/ui";

type RankedPolicy = {
  cluster_id: string;
  summary?: string;
  domain?: string;
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
                    href={`/${locale}/analytics/clusters/${item.cluster_id}`}
                    className="font-medium text-gray-900 hover:text-accent dark:text-slate-100 dark:hover:text-indigo-300"
                  >
                    {item.summary ?? item.cluster_id}
                  </Link>
                  {item.domain && (
                    <div className="mt-1">
                      <DomainBadge domain={item.domain} />
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
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </PageShell>
  );
}
