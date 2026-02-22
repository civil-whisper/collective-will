type Props = {
  status: "valid" | "invalid" | "unknown" | "verifying";
};

const CONFIG: Record<Props["status"], {label: string; classes: string}> = {
  valid: {
    label: "Chain Valid",
    classes: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  },
  invalid: {
    label: "Chain Broken",
    classes: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  },
  unknown: {
    label: "Unverified",
    classes: "bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-400",
  },
  verifying: {
    label: "Verifying…",
    classes: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
  },
};

export function ChainStatusBadge({status}: Props) {
  const {label, classes} = CONFIG[status];

  return (
    <span
      role="status"
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${classes}`}
    >
      {status === "valid" && (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      )}
      {status === "invalid" && (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      )}
      {label}
    </span>
  );
}
