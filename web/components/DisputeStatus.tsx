type Props = {
  status: "none" | "open" | "resolved";
  resolution?: string;
};

export function DisputeStatus({status, resolution}: Props) {
  if (status === "open") {
    return (
      <span
        role="status"
        className="inline-flex items-center gap-1.5 rounded-full bg-yellow-100 px-3 py-1 text-sm font-medium text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
        Under automated review
      </span>
    );
  }
  if (status === "resolved") {
    return (
      <span
        role="status"
        className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800 dark:bg-green-900/40 dark:text-green-300"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
        Resolved{resolution ? `: ${resolution}` : ""}
      </span>
    );
  }
  return null;
}
