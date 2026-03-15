import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {Card, PageShell} from "@/components/ui";

export async function generateMetadata() {
  const t = await getTranslations("verificationGuide");
  return {title: t("pageTitle")};
}

export default async function IndependentVerificationPage() {
  const t = await getTranslations("verificationGuide");
  const locale = await getLocale();

  const quickSteps = [
    t("quickSteps.1"),
    t("quickSteps.2"),
    t("quickSteps.3"),
  ];
  const auditorSteps = [
    t("auditorSteps.1"),
    t("auditorSteps.2"),
    t("auditorSteps.3"),
    t("auditorSteps.4"),
    t("auditorSteps.5"),
  ];

  return (
    <PageShell title={t("pageTitle")} subtitle={t("pageSubtitle")}>
      <Card>
        <h2 className="text-lg font-semibold">{t("whyTitle")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
          {t("whyBody")}
        </p>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="text-lg font-semibold">{t("quickTitle")}</h2>
          <ol className="mt-3 list-decimal space-y-2 ps-5 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
            {quickSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">{t("filesTitle")}</h2>
          <ul className="mt-3 space-y-2 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
            <li>{t("files.bundle")}</li>
            <li>{t("files.manifest")}</li>
            <li>{t("files.ots")}</li>
          </ul>
        </Card>
      </div>

      <Card>
        <h2 className="text-lg font-semibold">{t("auditorTitle")}</h2>
        <ol className="mt-3 list-decimal space-y-2 ps-5 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
          {auditorSteps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="text-lg font-semibold">{t("provesTitle")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
            {t("provesBody")}
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">{t("limitsTitle")}</h2>
          <p className="mt-3 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
            {t("limitsBody")}
          </p>
        </Card>
      </div>

      <Card>
        <h2 className="text-lg font-semibold">{t("costTitle")}</h2>
        <p className="mt-3 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
          {t("costBody")}
        </p>
      </Card>

      <Card>
        <details>
          <summary className="cursor-pointer text-lg font-semibold">{t("advancedTitle")}</summary>
          <p className="mt-3 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
            {t("advancedBody")}
          </p>
          <pre className="mt-3 overflow-x-auto rounded-md bg-gray-50 p-4 text-xs dark:bg-slate-900">
            <code>{t("advancedCommand")}</code>
          </pre>
        </details>
      </Card>

      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">{t("ctaTitle")}</h2>
            <p className="mt-2 text-sm leading-relaxed text-gray-700 dark:text-slate-300">
              {t("ctaBody")}
            </p>
          </div>
          <Link
            href={`/${locale}/collective-concerns/audit-bundles`}
            className="inline-flex items-center rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            {t("ctaButton")}
          </Link>
        </div>
      </Card>
    </PageShell>
  );
}
