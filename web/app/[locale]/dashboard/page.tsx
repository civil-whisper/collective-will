import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {DisputeButton} from "@/components/DisputeButton";
import {DisputeStatus} from "@/components/DisputeStatus";
import {apiGet} from "@/lib/api";

const DEMO_EMAIL = process.env.NEXT_PUBLIC_DEMO_EMAIL ?? "demo@example.com";

type Submission = {
  id: string;
  raw_text: string;
  status: string;
  hash: string;
  candidate?: {
    title: string;
    summary: string;
    domain: string;
    confidence: number;
  };
  cluster?: {
    id: string;
    summary: string;
    approval_count: number;
  };
  dispute_status?: "open" | "resolved" | null;
};

type Vote = {
  id: string;
  cycle_id: string;
  approved_cluster_ids?: string[];
};

async function getSubmissions(): Promise<Submission[]> {
  return apiGet<Submission[]>("/user/dashboard/submissions").catch(() => []);
}

async function getVotes(): Promise<Vote[]> {
  return apiGet<Vote[]>("/user/dashboard/votes").catch(() => []);
}

export default async function DashboardPage() {
  const t = await getTranslations("dashboard");
  const locale = await getLocale();
  const [submissions, votes] = await Promise.all([getSubmissions(), getVotes()]);

  return (
    <section>
      <h1>{t("title")}</h1>

      <div style={{display: "grid", gap: "1rem", gridTemplateColumns: "1fr 1fr", marginBottom: "2rem"}}>
        <div style={{padding: "1rem", border: "1px solid #ddd"}}>
          <strong>{t("totalSubmissions")}</strong>: {submissions.length}
        </div>
        <div style={{padding: "1rem", border: "1px solid #ddd"}}>
          <strong>{t("totalVotes")}</strong>: {votes.length}
        </div>
      </div>

      <h2>{t("submissions")}</h2>
      {submissions.length === 0 ? (
        <p>{t("noSubmissions")}</p>
      ) : (
        <ul>
          {submissions.map((sub) => (
            <li key={sub.id} style={{marginBottom: "1rem", padding: "1rem", border: "1px solid #eee"}}>
              <p><strong>{sub.raw_text}</strong></p>
              <p>Status: {sub.status === "pending" ? t("processing") : sub.status}</p>
              {sub.candidate && (
                <div>
                  <p>→ {sub.candidate.title}: {sub.candidate.summary}</p>
                  <p>{sub.candidate.domain} | Confidence: {Math.round(sub.candidate.confidence * 100)}%</p>
                </div>
              )}
              {sub.cluster && (
                <p>
                  Cluster:{" "}
                  <Link href={`/${locale}/analytics/clusters/${sub.cluster.id}`}>
                    {sub.cluster.summary}
                  </Link>
                </p>
              )}
              {sub.dispute_status ? (
                <DisputeStatus status={sub.dispute_status === "open" ? "open" : "resolved"} />
              ) : (
                sub.status === "processed" && <DisputeButton submissionId={sub.id} />
              )}
            </li>
          ))}
        </ul>
      )}

      <h2>{t("votes")}</h2>
      {votes.length === 0 ? (
        <p>{t("noVotes")}</p>
      ) : (
        <ul>
          {votes.map((vote) => (
            <li key={vote.id}>Cycle: {vote.cycle_id}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
