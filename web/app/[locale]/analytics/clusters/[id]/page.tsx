import {getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";

type PolicyCandidatePublic = {
  id: string;
  title: string;
  summary: string;
  domain: string;
  confidence: number;
};

type ClusterDetail = {
  id: string;
  summary: string;
  summary_en?: string;
  domain: string;
  member_count: number;
  approval_count: number;
  variance_flag: boolean;
  candidates: PolicyCandidatePublic[];
  grouping_rationale?: string;
};

type Props = {
  params: Promise<{id: string}>;
};

export default async function ClusterDetailPage({params}: Props) {
  const {id} = await params;
  const t = await getTranslations("analytics");
  const cluster = await apiGet<ClusterDetail>(`/analytics/clusters/${id}`).catch(() => null);

  if (!cluster) {
    return <p>{t("noClusters")}</p>;
  }

  return (
    <section>
      <h1>{cluster.summary}</h1>
      {cluster.summary_en && <p>{cluster.summary_en}</p>}
      {cluster.grouping_rationale && <p><em>{cluster.grouping_rationale}</em></p>}
      <p>{t("domain")}: {cluster.domain}</p>
      <p>{t("memberCount")}: {cluster.member_count}</p>
      <p>{t("approvalCount")}: {cluster.approval_count}</p>
      {cluster.variance_flag && <p>⚠️ {t("varianceFlag")}</p>}
      <h2>{t("memberCount")}</h2>
      <ul>
        {cluster.candidates.map((candidate) => (
          <li key={candidate.id}>
            <strong>{candidate.title}</strong>: {candidate.summary}
            <br />
            {t("domain")}: {candidate.domain} | Confidence: {Math.round(candidate.confidence * 100)}%
          </li>
        ))}
      </ul>
    </section>
  );
}
