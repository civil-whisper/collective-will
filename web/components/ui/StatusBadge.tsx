type Variant = "success" | "warning" | "error" | "info" | "neutral";

const VARIANT_CLASSES: Record<Variant, string> = {
  success: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  warning: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
  error: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  info: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  neutral: "bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-400",
};

type Props = {
  label: string;
  variant?: Variant;
};

export function StatusBadge({label, variant = "neutral"}: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${VARIANT_CLASSES[variant]}`}
    >
      {label}
    </span>
  );
}
