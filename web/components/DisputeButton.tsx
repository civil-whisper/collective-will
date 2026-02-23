"use client";

import {FormEvent, useState} from "react";
import {useTranslations} from "next-intl";

import {apiPost} from "@/lib/api";

type Props = {
  submissionId: string;
  disabled?: boolean;
};

export function DisputeButton({submissionId, disabled}: Props) {
  const t = useTranslations("dashboard");
  const [showForm, setShowForm] = useState(false);
  const [disputeType, setDisputeType] = useState<"canonicalization" | "cluster_assignment">("canonicalization");
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "sent" | "error">("idle");

  const sendDispute = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("loading");
    try {
      await apiPost(`/api/user/dashboard/disputes/${submissionId}`, {
        entity_type: disputeType,
        entity_id: submissionId,
        dispute_type: disputeType,
        reason: reason || undefined,
      });
      setStatus("sent");
      setShowForm(false);
    } catch {
      setStatus("error");
    }
  };

  if (status === "sent") {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400">
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
        </svg>
        {t("underReview")}
      </span>
    );
  }

  if (disabled) {
    return null;
  }

  return (
    <div>
      {!showForm ? (
        <button
          onClick={() => setShowForm(true)}
          type="button"
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          {t("openDispute")}
        </button>
      ) : (
        <form onSubmit={sendDispute} className="mt-2 space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-800">
          <fieldset>
            <legend className="mb-2 text-sm font-semibold">{t("disputeType")}</legend>
            <div className="flex gap-2">
              <label
                className={`cursor-pointer rounded-lg border px-3 py-2 text-sm transition-colors ${
                  disputeType === "canonicalization"
                    ? "border-accent bg-accent/10 font-medium text-accent"
                    : "border-gray-300 text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                }`}
              >
                <input
                  type="radio"
                  name="disputeType"
                  value="canonicalization"
                  checked={disputeType === "canonicalization"}
                  onChange={() => setDisputeType("canonicalization")}
                  className="sr-only"
                />
                {t("badCanonicalization")}
              </label>
              <label
                className={`cursor-pointer rounded-lg border px-3 py-2 text-sm transition-colors ${
                  disputeType === "cluster_assignment"
                    ? "border-accent bg-accent/10 font-medium text-accent"
                    : "border-gray-300 text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                }`}
              >
                <input
                  type="radio"
                  name="disputeType"
                  value="cluster_assignment"
                  checked={disputeType === "cluster_assignment"}
                  onChange={() => setDisputeType("cluster_assignment")}
                  className="sr-only"
                />
                {t("wrongCluster")}
              </label>
            </div>
          </fieldset>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300">
              {t("reason")}
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none transition-colors placeholder:text-gray-400 focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-slate-600 dark:bg-slate-900 dark:placeholder:text-slate-500"
              />
            </label>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={status === "loading"}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
            >
              {t("submit") ?? "Submit"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              Cancel
            </button>
          </div>
          {status === "error" && (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              Error submitting dispute
            </p>
          )}
        </form>
      )}
    </div>
  );
}
