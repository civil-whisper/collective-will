import {Card} from "./Card";

type Props = {
  label: string;
  value: string | number;
  trend?: string;
  trendDirection?: "up" | "down" | "neutral";
};

export function MetricCard({label, value, trend, trendDirection}: Props) {
  const trendColor =
    trendDirection === "up"
      ? "text-green-600 dark:text-green-400"
      : trendDirection === "down"
        ? "text-red-600 dark:text-red-400"
        : "text-gray-500 dark:text-slate-400";

  const trendArrow =
    trendDirection === "up" ? "↑" : trendDirection === "down" ? "↓" : "";

  return (
    <Card>
      <p className="text-sm font-medium text-gray-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-3xl font-bold tracking-tight">{value}</p>
      {trend && (
        <p className={`mt-1 text-sm font-medium ${trendColor}`}>
          {trendArrow} {trend}
        </p>
      )}
    </Card>
  );
}
