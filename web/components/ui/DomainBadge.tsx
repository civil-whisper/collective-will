const DOMAIN_COLORS: Record<string, string> = {
  governance: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  economy: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  rights: "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300",
  foreign_policy: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  religion: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  ethnic: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
  justice: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300",
  other: "bg-gray-100 text-gray-800 dark:bg-slate-700 dark:text-slate-300",
};

type Props = {
  domain: string;
};

export function DomainBadge({domain}: Props) {
  const colors = DOMAIN_COLORS[domain] ?? DOMAIN_COLORS.other;
  const label = domain.replace(/_/g, " ");

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${colors}`}
    >
      {label}
    </span>
  );
}
