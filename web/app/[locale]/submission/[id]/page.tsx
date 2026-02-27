import Link from "next/link";
import {redirect} from "next/navigation";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";
import {PageShell, Card} from "@/components/ui";

type CandidateLocation =
  | {status: "unclustered"}
  | {status: "clustered"; cluster_id: string};

type Props = {
  params: Promise<{id: string}>;
};

export default async function SubmissionRedirectPage({params}: Props) {
  const {id} = await params;
  const locale = await getLocale();
  const t = await getTranslations("analytics");

  const location = await apiGet<CandidateLocation>(
    `/analytics/candidate/${id}/location`,
  ).catch(() => null);

  if (location === null) {
    return (
      <PageShell title={t("submissionNotFound")}>
        <Card>
          <p className="py-8 text-center text-gray-500 dark:text-slate-400">
            {t("submissionNotFoundDescription")}
          </p>
          <div className="text-center">
            <Link
              href={`/${locale}/collective-concerns`}
              className="text-sm font-medium text-accent hover:underline"
            >
              {t("backToCollectiveConcerns")}
            </Link>
          </div>
        </Card>
      </PageShell>
    );
  }

  if (location.status === "clustered") {
    redirect(
      `/${locale}/collective-concerns/clusters/${location.cluster_id}#candidate-${id}`,
    );
  }

  redirect(`/${locale}/collective-concerns#candidate-${id}`);
}
