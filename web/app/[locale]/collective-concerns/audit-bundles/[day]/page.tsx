import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";
import {notFound} from "next/navigation";

import {Card, MetricCard, PageShell, StatusBadge} from "@/components/ui";
import {absoluteApiUrl, type AuditBundleDayResponse, formatAuditDate, timestampStatusVariant} from "@/lib/audit-bundles";
import {apiGet} from "@/lib/api";

type PageProps = {
  params: Promise<{
    day: string;
  }>;
};

async function getAuditBundleDay(day: string): Promise<AuditBundleDayResponse | null> {
  return apiGet<AuditBundleDayResponse>(`/analytics/audit-bundles/${day}`).catch(() => null);
}

export async function generateMetadata() {
  const t = await getTranslations("analytics");
  return {title: t("auditSnapshotDetailTitle")};
}

export default async function AuditBundleDayPage({params}: PageProps) {
  const {day} = await params;
  const t = await getTranslations("analytics");
  const locale = await getLocale();
  const bundle = await getAuditBundleDay(day);
  if (!bundle) {
    notFound();
  }

  return (
    <PageShell title={t("auditSnapshotDetailTitle")} subtitle={formatAuditDate(bundle.day_utc, locale)}>
      <div>
        <Link
          href={`/${locale}/collective-concerns/audit-bundles`}
          className="text-sm font-medium text-accent hover:underline"
        >
          {t("backToAuditSnapshots")}
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label={t("totalEntries")} value={(bundle.entry_count ?? 0).toLocaleString()} />
        <MetricCard label={t("bundleHashMatchesManifest")} value={bundle.bundle_hash_matches_manifest ? t("yes") : t("no")} />
        <MetricCard label={t("otsProofPresent")} value={bundle.timestamping.ots_proof_present ? t("yes") : t("no")} />
        <Card>
          <p className="text-sm font-medium text-gray-500 dark:text-slate-400">{t("timestampingStatus")}</p>
          <div className="mt-3">
            <StatusBadge label={bundle.timestamping.status ?? t("timestampingUnknown")} variant={timestampStatusVariant(bundle.timestamping.status)} />
          </div>
        </Card>
      </div>

      <Card>
        <h2 className="text-lg font-semibold">{t("auditSnapshotDetails")}</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="font-medium text-gray-600 dark:text-slate-300">{t("bundleSha256Label")}</dt>
            <dd className="mt-1 break-all font-mono text-xs">{bundle.bundle_sha256 ?? t("notAvailable")}</dd>
          </div>
          <div>
            <dt className="font-medium text-gray-600 dark:text-slate-300">{t("dailyMerkleRootLabel")}</dt>
            <dd className="mt-1 break-all font-mono text-xs">{bundle.daily_merkle_root ?? t("notAvailable")}</dd>
          </div>
          <div>
            <dt className="font-medium text-gray-600 dark:text-slate-300">{t("generatedAtLabel")}</dt>
            <dd className="mt-1">{bundle.generated_at ?? t("notAvailable")}</dd>
          </div>
          <div>
            <dt className="font-medium text-gray-600 dark:text-slate-300">{t("verifiedBeforeLabel")}</dt>
            <dd className="mt-1">{bundle.timestamping.verified_before ?? t("notAvailable")}</dd>
          </div>
          <div>
            <dt className="font-medium text-gray-600 dark:text-slate-300">{t("bitcoinBlockHeightLabel")}</dt>
            <dd className="mt-1">{bundle.timestamping.bitcoin_block_height ?? t("notAvailable")}</dd>
          </div>
        </dl>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold">{t("downloadProofFiles")}</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          <a
            href={absoluteApiUrl(bundle.download_urls.bundle) ?? undefined}
            className="inline-flex items-center rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            {t("downloadBundle")}
          </a>
          <a
            href={absoluteApiUrl(bundle.download_urls.manifest) ?? undefined}
            className="inline-flex items-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {t("downloadManifest")}
          </a>
          <a
            href={absoluteApiUrl(bundle.download_urls.ots_proof) ?? undefined}
            className="inline-flex items-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {t("downloadOtsProof")}
          </a>
        </div>
      </Card>

      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">{t("verificationGuideTitle")}</h2>
            <p className="mt-2 text-sm text-gray-700 dark:text-slate-300">
              {t("verificationGuideBody")}
            </p>
          </div>
          <Link
            href={`/${locale}/independent-verification`}
            className="inline-flex items-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {t("openVerificationGuide")}
          </Link>
        </div>
      </Card>
    </PageShell>
  );
}
