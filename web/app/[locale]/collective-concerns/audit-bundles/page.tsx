import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {Card, PageShell, StatusBadge} from "@/components/ui";
import {absoluteApiUrl, type AuditBundleListResponse, formatAuditDate, timestampStatusVariant} from "@/lib/audit-bundles";
import {apiGet} from "@/lib/api";

async function getAuditBundles(): Promise<AuditBundleListResponse> {
  return apiGet<AuditBundleListResponse>("/analytics/audit-bundles").catch(() => ({
    schema_version: 1,
    updated_at: null,
    days: [],
  }));
}

export async function generateMetadata() {
  const t = await getTranslations("analytics");
  return {title: t("auditSnapshotsTitle")};
}

export default async function AuditBundlesPage() {
  const t = await getTranslations("analytics");
  const locale = await getLocale();
  const data = await getAuditBundles();

  return (
    <PageShell title={t("auditSnapshotsTitle")} subtitle={t("auditSnapshotsDescription")}>
      {data.days.length === 0 ? (
        <Card>
          <p className="py-4 text-center text-sm text-gray-500 dark:text-slate-400">
            {t("noAuditSnapshots")}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {data.days.map((day) => (
            <Card key={day.day_utc}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold">{formatAuditDate(day.day_utc, locale)}</h2>
                    <StatusBadge
                      label={day.timestamping_status ?? t("timestampingUnknown")}
                      variant={timestampStatusVariant(day.timestamping_status)}
                    />
                  </div>
                  <div className="mt-3 grid gap-2 text-sm text-gray-600 dark:text-slate-300 sm:grid-cols-2">
                    <p>{t("auditSnapshotEntries", {count: day.entry_count ?? 0})}</p>
                    <p className="break-all">{t("auditSnapshotMerkleRoot", {root: day.daily_merkle_root ?? t("notAvailable")})}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link
                    href={`/${locale}/collective-concerns/audit-bundles/${day.day_utc}`}
                    className="inline-flex items-center rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90"
                  >
                    {t("viewAuditSnapshot")}
                  </Link>
                  <a
                    href={absoluteApiUrl(day.download_urls.manifest) ?? undefined}
                    className="inline-flex items-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
                  >
                    {t("downloadManifest")}
                  </a>
                  <a
                    href={absoluteApiUrl(day.download_urls.bundle) ?? undefined}
                    className="inline-flex items-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
                  >
                    {t("downloadBundle")}
                  </a>
                  <a
                    href={absoluteApiUrl(day.download_urls.ots_proof) ?? undefined}
                    className="inline-flex items-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
                  >
                    {t("downloadOtsProof")}
                  </a>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </PageShell>
  );
}
