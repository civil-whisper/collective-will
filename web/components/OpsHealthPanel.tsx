import {Card, StatusBadge} from "@/components/ui";

export type OpsServiceStatus = {
  name: string;
  status: "ok" | "degraded" | "error" | "unknown";
  detail?: string | null;
};

const STATUS_VARIANT: Record<OpsServiceStatus["status"], "success" | "warning" | "error" | "neutral"> = {
  ok: "success",
  degraded: "warning",
  error: "error",
  unknown: "neutral",
};

export function OpsHealthPanel({
  title,
  services,
}: {
  title: string;
  services: OpsServiceStatus[];
}) {
  return (
    <Card>
      <h2 className="mb-3 text-lg font-semibold">{title}</h2>
      <div className="space-y-2">
        {services.map((service) => (
          <div
            key={service.name}
            className="flex items-start justify-between gap-3 rounded-md border border-gray-200 px-3 py-2 dark:border-slate-700"
          >
            <div>
              <p className="text-sm font-medium">{service.name}</p>
              {service.detail && (
                <p className="text-xs text-gray-500 dark:text-slate-400">{service.detail}</p>
              )}
            </div>
            <StatusBadge
              label={service.status}
              variant={STATUS_VARIANT[service.status]}
            />
          </div>
        ))}
      </div>
    </Card>
  );
}
