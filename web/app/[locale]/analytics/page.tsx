import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";

type Cluster = {
  id: string;
  summary: string;
  domain: string;
  member_count: number;
  approval_count: number;
  variance_flag: boolean;
};

export default async function AnalyticsPage() {
  const t = await getTranslations("analytics");
  const locale = await getLocale();
  const clusters = await apiGet<Cluster[]>("/analytics/clusters").catch(() => []);

  return (
    <section>
      <h1>{t("clusters")}</h1>
      {clusters.length === 0 ? (
        <p>{t("noClusters")}</p>
      ) : (
        <ul>
          {clusters.map((cluster) => (
            <li key={cluster.id} style={{marginBottom: "1rem", padding: "1rem", border: "1px solid #ddd"}}>
              <Link href={`/${locale}/analytics/clusters/${cluster.id}`}>
                <strong>{cluster.summary}</strong>
              </Link>
              <br />
              {t("domain")}: {cluster.domain} | {t("memberCount")}: {cluster.member_count} | {t("approvalCount")}: {cluster.approval_count}
              {cluster.variance_flag && <span> ⚠️ {t("varianceFlag")}</span>}
            </li>
          ))}
        </ul>
      )}
      <p>
        <Link href={`/${locale}/analytics/top-policies`}>{t("topPolicies")}</Link>
        {" | "}
        <Link href={`/${locale}/analytics/evidence`}>{t("evidence")}</Link>
      </p>
    </section>
  );
}
