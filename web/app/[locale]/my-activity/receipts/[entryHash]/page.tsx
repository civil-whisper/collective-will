import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";
import {notFound, redirect} from "next/navigation";

import {Card, PageShell, StatusBadge} from "@/components/ui";
import {apiGet} from "@/lib/api";
import {absoluteApiUrl} from "@/lib/audit-bundles";
import {buildBearerHeaders, getBackendAccessToken} from "@/lib/backend-auth";
import {eventDescription} from "@/lib/evidence";
import {
  type ReceiptEntry,
  type ReceiptListResponse,
  type ReceiptVerification,
  formatReceiptTimestamp,
  receiptBadgeVariant,
} from "@/lib/receipts";

type PageProps = {
  params: Promise<{
    entryHash: string;
  }>;
};

async function getReceipts(accessToken: string): Promise<ReceiptEntry[]> {
  const response = await apiGet<ReceiptListResponse>("/user/dashboard/receipts", {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => null);
  return response?.entries ?? [];
}

async function getReceiptVerification(accessToken: string, entryHash: string): Promise<ReceiptVerification | null> {
  return apiGet<ReceiptVerification>(`/user/dashboard/receipts/${entryHash}/verify`, {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => null);
}

export async function generateMetadata() {
  const t = await getTranslations("receiptVerification");
  return {title: t("title")};
}

export default async function ReceiptVerificationPage({params}: PageProps) {
  const accessToken = await getBackendAccessToken();
  const locale = await getLocale();
  const {entryHash} = await params;
  const t = await getTranslations("receiptVerification");
  const tAnalytics = await getTranslations("analytics");

  if (!accessToken) {
    redirect(`/${locale}/sign-in`);
  }

  const receipts = await getReceipts(accessToken);
  const receipt = receipts.find((entry) => entry.hash === entryHash);
  if (!receipt) {
    notFound();
  }

  const verification = await getReceiptVerification(accessToken, entryHash);
  if (!verification) {
    notFound();
  }

  return (
    <PageShell
      title={t("title")}
      subtitle={t("subtitle")}
    >
      <div>
        <Link
          href={`/${locale}/my-activity`}
          className="text-sm font-medium text-accent hover:underline"
        >
          {t("backToActivity")}
        </Link>
      </div>

      <Card>
        <h2 className="text-lg font-semibold">{t("whatHappenedTitle")}</h2>
        <p className="mt-3 font-medium">{eventDescription(receipt, tAnalytics)}</p>
        <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
          {t("recordedAt", {timestamp: formatReceiptTimestamp(receipt.timestamp, locale)})}
        </p>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold">{t("verificationStatusTitle")}</h2>
        <div className="mt-3 flex items-center gap-3">
          <StatusBadge
            label={t(`states.${verification.status}.label`)}
            variant={receiptBadgeVariant(verification.status)}
          />
          <span className="text-sm text-gray-600 dark:text-slate-300">
            {t(`states.${verification.status}.description`)}
          </span>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="text-lg font-semibold">{t("whatThisProvesTitle")}</h2>
          <p className="mt-3 text-sm text-gray-700 dark:text-slate-300">{t("whatThisProvesBody")}</p>
        </Card>
        <Card>
          <h2 className="text-lg font-semibold">{t("whatThisDoesNotProveTitle")}</h2>
          <p className="mt-3 text-sm text-gray-700 dark:text-slate-300">{t("whatThisDoesNotProveBody")}</p>
        </Card>
      </div>

      <Card>
        <h2 className="text-lg font-semibold">{t("downloadsTitle")}</h2>
        <div className="mt-3 space-y-2 text-sm">
          <div className="flex items-center justify-between gap-4">
            <span>{t("proofFileBundle")}</span>
            {verification.download_urls.bundle ? (
              <a
                href={absoluteApiUrl(verification.download_urls.bundle) ?? undefined}
                className="font-medium text-accent hover:underline"
              >
                {t("downloadProofFiles")}
              </a>
            ) : (
              <span className="text-gray-500 dark:text-slate-400">{t("proofFileUnavailable")}</span>
            )}
          </div>
          <div className="flex items-center justify-between gap-4">
            <span>{t("proofFileManifest")}</span>
            {verification.download_urls.manifest ? (
              <a
                href={absoluteApiUrl(verification.download_urls.manifest) ?? undefined}
                className="font-medium text-accent hover:underline"
              >
                {t("downloadProofFiles")}
              </a>
            ) : (
              <span className="text-gray-500 dark:text-slate-400">{t("proofFileUnavailable")}</span>
            )}
          </div>
          <div className="flex items-center justify-between gap-4">
            <span>{t("proofFileOts")}</span>
            {verification.download_urls.ots_proof ? (
              <a
                href={absoluteApiUrl(verification.download_urls.ots_proof) ?? undefined}
                className="font-medium text-accent hover:underline"
              >
                {t("downloadProofFiles")}
              </a>
            ) : (
              <span className="text-gray-500 dark:text-slate-400">{t("proofFileUnavailable")}</span>
            )}
          </div>
        </div>
      </Card>

      <Card>
        <details>
          <summary className="cursor-pointer text-lg font-semibold">{t("showTechnicalDetails")}</summary>
          <dl className="mt-4 space-y-3 text-sm">
            <div className="flex flex-col gap-1">
              <dt className="font-medium text-gray-600 dark:text-slate-300">{t("entryHashLabel")}</dt>
              <dd className="font-mono text-xs break-all">{receipt.hash}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="font-medium text-gray-600 dark:text-slate-300">{t("receiptTokenLabel")}</dt>
              <dd className="font-mono text-xs break-all">{receipt.receipt_token}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="font-medium text-gray-600 dark:text-slate-300">{t("bundleDayLabel")}</dt>
              <dd>{verification.bundle_day || t("notAvailable")}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="font-medium text-gray-600 dark:text-slate-300">{t("includedInBundleLabel")}</dt>
              <dd>{verification.included_in_public_bundle ? t("yes") : t("no")}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="font-medium text-gray-600 dark:text-slate-300">{t("manifestMatchLabel")}</dt>
              <dd>{verification.bundle_hash_matches_manifest ? t("yes") : t("no")}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="font-medium text-gray-600 dark:text-slate-300">{t("otsProofLabel")}</dt>
              <dd>{verification.ots_proof_present ? t("yes") : t("no")}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="font-medium text-gray-600 dark:text-slate-300">{t("otsVerifiedLabel")}</dt>
              <dd>{verification.ots_verified ? t("yes") : t("no")}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="font-medium text-gray-600 dark:text-slate-300">{t("verifiedBeforeLabel")}</dt>
              <dd>{verification.verified_before ?? t("notAvailable")}</dd>
            </div>
          </dl>
        </details>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold">{t("howIndependentVerificationWorks")}</h2>
        <p className="mt-3 text-sm text-gray-700 dark:text-slate-300">{t("independentVerificationBody")}</p>
        <Link
          href={`/${locale}/independent-verification`}
          className="mt-3 inline-flex text-sm font-medium text-accent hover:underline"
        >
          {t("openVerificationGuide")}
        </Link>
      </Card>
    </PageShell>
  );
}
