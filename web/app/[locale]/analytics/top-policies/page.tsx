import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";

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
      <section>
        <h1>{t("topPolicies")}</h1>
        <p>{t("noCycles")}</p>
      </section>
    );
  }

  return (
    <section>
      <h1>{t("topPolicies")}</h1>
      <ol>
        {ranked.map((item, index) => (
          <li key={item.cluster_id} style={{marginBottom: "0.5rem"}}>
            <strong>{t("rank")} {index + 1}</strong>:{" "}
            <Link href={`/${locale}/analytics/clusters/${item.cluster_id}`}>
              {item.summary ?? item.cluster_id}
            </Link>
            {" — "}
            {t("approvalRate")}: {Math.round(item.approval_rate * 100)}%
            {" | "}
            {t("approvalCount")}: {item.approval_count}
            {item.domain && <span> | {t("domain")}: {item.domain}</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}
