import Link from "next/link";
import {getLocale, getTranslations} from "next-intl/server";

import {apiGet} from "@/lib/api";
import {PageShell, Card, TopicBadge} from "@/components/ui";

type CandidateLocation =
  | {status: "unclustered"}
  | {status: "clustered"; cluster_id: string};

type PipelineEntry = {
  id: number;
  timestamp: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
};

type CandidateSnapshot = {
  id: string;
  submission_id: string;
  title: string;
  summary: string;
  policy_topic: string;
  policy_key: string;
  actor_scope: string;
  action_mechanism: string;
  target_scope: string;
  ballot_readiness: "ballot-ready" | "needs-refinement" | "discussion-only";
  ballot_readiness_reason: string | null;
  confidence: number;
  raw_text: string;
  language: string | null;
};

type CandidatePipelineHistory = {
  submission_id: string;
  raw_text: string;
  status: string;
  candidate_ids: string[];
  entries: PipelineEntry[];
  candidate: CandidateSnapshot;
  location: CandidateLocation;
};

type Props = {
  params: Promise<{id: string}>;
};

function StageBadge({
  stage,
  t,
}: {
  stage: "ballot-ready" | "needs-refinement" | "discussion-only";
  t: (key: string, values?: Record<string, string | number>) => string;
}) {
  const labelByStage = {
    "ballot-ready": t("stageBallotReady"),
    "needs-refinement": t("stageNeedsRefinement"),
    "discussion-only": t("stageDiscussionOnly"),
  };
  const classNameByStage = {
    "ballot-ready": "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
    "needs-refinement": "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
    "discussion-only": "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${classNameByStage[stage]}`}>
      {labelByStage[stage]}
    </span>
  );
}

export default async function SubmissionRedirectPage({params}: Props) {
  const {id} = await params;
  const locale = await getLocale();
  const t = await getTranslations("analytics");

  const history = await apiGet<CandidatePipelineHistory>(
    `/analytics/candidate/${id}/pipeline-history`,
  ).catch(() => null);

  if (history === null) {
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

  const currentLocationHref = history.location.status === "clustered"
    ? `/${locale}/collective-concerns/clusters/${history.location.cluster_id}#candidate-${id}`
    : `/${locale}/collective-concerns#candidate-${id}`;

  return (
    <PageShell
      title={history.candidate.title}
      actions={(
        <div className="flex items-center gap-2">
          <TopicBadge topic={history.candidate.policy_topic} />
          <StageBadge stage={history.candidate.ballot_readiness} t={t} />
        </div>
      )}
    >
      <Card>
        <div className="space-y-3">
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-slate-500">
              {t("userSubmission")}
            </p>
            <blockquote
              className="border-s-2 border-gray-300 ps-3 text-sm text-gray-700 dark:border-slate-600 dark:text-slate-300"
              dir={history.candidate.language === "fa" ? "rtl" : "ltr"}
            >
              {history.raw_text}
            </blockquote>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-slate-500">
              {t("aiInterpretation")}
            </p>
            <p className="font-medium">{history.candidate.summary}</p>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-500 dark:text-slate-400">
              <span>{t("semanticActor")}: {history.candidate.actor_scope}</span>
              <span>{t("semanticMechanism")}: {history.candidate.action_mechanism}</span>
              <span>{t("semanticTarget")}: {history.candidate.target_scope}</span>
              <span>{t("aiConfidence")}: {Math.round(history.candidate.confidence * 100)}%</span>
            </div>
            {history.candidate.ballot_readiness_reason && (
              <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
                {history.candidate.ballot_readiness_reason}
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <Link href={currentLocationHref} className="font-medium text-accent hover:underline">
              {t("viewCurrentLocation")} →
            </Link>
            <Link href={`/${locale}/collective-concerns/evidence?entity=${history.submission_id}`} className="font-medium text-accent hover:underline">
              {t("viewAuditTrail")} →
            </Link>
          </div>
        </div>
      </Card>

      <div>
        <h2 className="mb-3 text-lg font-semibold">{t("pipelineHistory")}</h2>
        <div className="space-y-3">
          {history.entries.map((entry) => (
            <Card key={entry.id}>
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                      {entry.event_type.replace(/_/g, " ")}
                    </span>
                    <span className="text-xs text-gray-400 dark:text-slate-500">
                      {new Date(entry.timestamp).toLocaleString(locale === "fa" ? "fa-IR" : "en-US")}
                    </span>
                  </div>
                  <pre className="mt-2 overflow-auto rounded-md bg-gray-50 p-3 text-xs text-gray-700 dark:bg-slate-900 dark:text-slate-300">
                    {JSON.stringify(entry.payload, null, 2)}
                  </pre>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </PageShell>
  );
}
