import {getLocale, getTranslations} from "next-intl/server";
import Link from "next/link";
import {redirect} from "next/navigation";

import {OpsEventFeed, type OpsEvent} from "@/components/OpsEventFeed";
import {OpsHealthPanel, type OpsServiceStatus} from "@/components/OpsHealthPanel";
import {Card, PageShell} from "@/components/ui";
import {apiGet} from "@/lib/api";
import {buildBearerHeaders, getBackendAccessToken} from "@/lib/backend-auth";

type OpsStatusResponse = {
  generated_at: string;
  require_admin: boolean;
  services: OpsServiceStatus[];
};

type OpsJobStatus = {
  name: string;
  status: "ok" | "degraded" | "error" | "unknown";
  last_run: string | null;
  detail: string | null;
};

type PipelineStepHealth = {
  step: string;
  event_count: number;
  latest_at: string | null;
};

type PipelineHealthResponse = {
  generated_at: string;
  total_degradation_events: number;
  by_step: PipelineStepHealth[];
  model_fallback_count: number;
};

type OpsEventLevel = "info" | "warning" | "error";

async function getStatus(accessToken: string): Promise<OpsStatusResponse | null> {
  return apiGet<OpsStatusResponse>("/ops/status", {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => null);
}

async function getEvents(
  accessToken: string,
  params: {correlationId: string; level: OpsEventLevel | ""; eventType: string},
): Promise<OpsEvent[]> {
  const query = new URLSearchParams({limit: "200"});
  if (params.correlationId) {
    query.set("correlation_id", params.correlationId);
  }
  if (params.level) {
    query.set("level", params.level);
  }
  if (params.eventType) {
    query.set("type", params.eventType);
  }

  return apiGet<OpsEvent[]>(`/ops/events?${query.toString()}`, {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => []);
}

async function getJobs(accessToken: string): Promise<OpsJobStatus[]> {
  return apiGet<OpsJobStatus[]>("/ops/jobs", {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => []);
}

async function getPipelineHealth(accessToken: string): Promise<PipelineHealthResponse | null> {
  return apiGet<PipelineHealthResponse>("/ops/pipeline-health?hours=24", {
    headers: buildBearerHeaders(accessToken),
  }).catch(() => null);
}

type OpsPageProps = {
  searchParams?: Promise<{cid?: string; level?: string; type?: string}>;
};

export async function generateMetadata() {
  const t = await getTranslations("ops");
  return { title: t("title") };
}

export default async function OpsPage({searchParams}: OpsPageProps) {
  const t = await getTranslations("ops");
  const locale = await getLocale();
  const query = searchParams ? await searchParams : {};
  const correlationId = (query.cid ?? "").trim();
  const selectedLevel = (query.level === "info" || query.level === "warning" || query.level === "error")
    ? query.level
    : "";
  const selectedEventType = (query.type ?? "").trim();
  const accessToken = await getBackendAccessToken();
  if (!accessToken) {
    redirect(`/${locale}/sign-in`);
  }

  const [status, events, jobs, pipelineHealth] = await Promise.all([
    getStatus(accessToken),
    getEvents(accessToken, {
      correlationId,
      level: selectedLevel,
      eventType: selectedEventType,
    }),
    getJobs(accessToken),
    getPipelineHealth(accessToken),
  ]);

  const buildOpsHref = (next: {cid?: string; level?: OpsEventLevel | ""; type?: string}) => {
    const params = new URLSearchParams();
    const nextCid = next.cid === undefined ? correlationId : next.cid;
    const nextLevel = next.level === undefined ? selectedLevel : next.level;
    const nextType = next.type === undefined ? selectedEventType : next.type;

    if (nextCid) {
      params.set("cid", nextCid);
    }
    if (nextLevel) {
      params.set("level", nextLevel);
    }
    if (nextType) {
      params.set("type", nextType);
    }
    const queryString = params.toString();
    return `/${locale}/ops${queryString ? `?${queryString}` : ""}`;
  };

  const chipClass = (active: boolean) =>
    `rounded-full px-3 py-1 text-xs font-medium transition-colors ${
      active
        ? "bg-accent text-white"
        : "bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
    }`;

  const levelFilters: Array<{key: OpsEventLevel | ""; label: string}> = [
    {key: "", label: t("allLevels")},
    {key: "error", label: t("errorsOnly")},
    {key: "warning", label: t("warningsOnly")},
    {key: "info", label: t("infoOnly")},
  ];
  const eventFilters: Array<{key: string; label: string}> = [
    {key: "", label: t("allEvents")},
    {key: "scheduler.pipeline", label: t("schedulerEvents")},
    {key: "api.request.failed", label: t("failedRequests")},
    {key: "api.request.completed", label: t("completedRequests")},
  ];
  const hasActiveFilters = Boolean(correlationId || selectedLevel || selectedEventType);

  return (
    <PageShell title={t("title")} subtitle={t("subtitle")}>
      {!status ? (
        <Card>
          <p className="text-sm text-gray-600 dark:text-slate-400">{t("unavailable")}</p>
        </Card>
      ) : (
        <>
          <OpsHealthPanel title={t("health")} services={status.services} />

          {pipelineHealth && (
            <Card>
              <h2 className="mb-1 text-lg font-semibold">{t("pipelineHealth")}</h2>
              <p className="mb-3 text-xs text-gray-500 dark:text-slate-400">
                {t("pipelineHealthDesc", {hours: "24"})}
              </p>
              {pipelineHealth.total_degradation_events === 0 && pipelineHealth.model_fallback_count === 0 ? (
                <p className="text-sm text-gray-500 dark:text-slate-400">{t("noDegradations")}</p>
              ) : (
                <>
                  <div className="mb-3 flex flex-wrap gap-4 text-sm">
                    <span>
                      <span className="font-medium text-amber-600 dark:text-amber-400">{pipelineHealth.total_degradation_events}</span>{" "}
                      {t("totalDegradations")}
                    </span>
                    <span>
                      <span className="font-medium text-amber-600 dark:text-amber-400">{pipelineHealth.model_fallback_count}</span>{" "}
                      {t("modelFallbacks")}
                    </span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-slate-700">
                          <th className="pb-2 pr-4 font-medium text-gray-600 dark:text-slate-400">{t("degradationStep")}</th>
                          <th className="pb-2 pr-4 text-right font-medium text-gray-600 dark:text-slate-400">{t("degradationCount")}</th>
                          <th className="pb-2 font-medium text-gray-600 dark:text-slate-400">{t("degradationLatest")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pipelineHealth.by_step
                          .filter((s) => s.event_count > 0)
                          .map((s) => (
                            <tr key={s.step} className="border-b border-gray-100 dark:border-slate-800">
                              <td className="py-1.5 pr-4 font-mono text-xs">{s.step}</td>
                              <td className="py-1.5 pr-4 text-right font-medium text-amber-600 dark:text-amber-400">{s.event_count}</td>
                              <td className="py-1.5 font-mono text-xs text-gray-500 dark:text-slate-400">{s.latest_at ?? "—"}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </Card>
          )}

          <Card>
            <h2 className="mb-3 text-lg font-semibold">{t("traceFilterTitle")}</h2>
            <form className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <label className="flex-1 text-sm">
                <span className="mb-1 block text-gray-600 dark:text-slate-400">{t("requestIdLabel")}</span>
                <input
                  type="text"
                  name="cid"
                  defaultValue={correlationId}
                  placeholder={t("requestIdPlaceholder")}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none transition-colors placeholder:text-gray-400 focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-slate-600 dark:bg-slate-800 dark:placeholder:text-slate-500"
                />
              </label>
              {selectedLevel && <input type="hidden" name="level" value={selectedLevel} />}
              {selectedEventType && <input type="hidden" name="type" value={selectedEventType} />}
              <button
                type="submit"
                className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
              >
                {t("applyFilter")}
              </button>
              {hasActiveFilters && (
                <Link
                  href={`/${locale}/ops`}
                  className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-center text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                >
                  {t("clearFilter")}
                </Link>
              )}
            </form>
            <div className="mt-3 space-y-2">
              <p className="text-xs font-medium text-gray-500 dark:text-slate-400">{t("quickFilters")}</p>
              <div className="flex flex-wrap gap-2">
                {levelFilters.map((filter) => (
                  <Link
                    key={`level-${filter.key || "all"}`}
                    href={buildOpsHref({level: filter.key})}
                    className={chipClass(selectedLevel === filter.key)}
                  >
                    {filter.label}
                  </Link>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {eventFilters.map((filter) => (
                  <Link
                    key={`type-${filter.key || "all"}`}
                    href={buildOpsHref({type: filter.key})}
                    className={chipClass(selectedEventType === filter.key)}
                  >
                    {filter.label}
                  </Link>
                ))}
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="mb-3 text-lg font-semibold">{t("jobs")}</h2>
            {jobs.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-slate-400">{t("noJobs")}</p>
            ) : (
              <div className="space-y-2">
                {jobs.map((job) => (
                  <div
                    key={job.name}
                    className="rounded-md border border-gray-200 px-3 py-2 dark:border-slate-700"
                  >
                    <p className="text-sm font-medium">{job.name}</p>
                    <p className="text-xs text-gray-500 dark:text-slate-400">
                      {t("status")}: {job.status}
                    </p>
                    {job.last_run && (
                      <p className="font-mono text-xs text-gray-500 dark:text-slate-400">
                        {t("lastRun")}: {job.last_run}
                      </p>
                    )}
                    {job.detail && (
                      <p className="text-xs text-gray-500 dark:text-slate-400">{job.detail}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <OpsEventFeed
            title={t("events")}
            emptyState={hasActiveFilters ? t("noEventsWithFilters") : t("noEvents")}
            clearFiltersHref={hasActiveFilters ? `/${locale}/ops` : undefined}
            clearFiltersLabel={hasActiveFilters ? t("clearFilter") : undefined}
            events={events}
          />
        </>
      )}
    </PageShell>
  );
}
