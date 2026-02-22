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
      await apiPost(`/user/dashboard/disputes/${submissionId}`, {
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
    return <span>🔍 {t("underReview")}</span>;
  }

  if (disabled) {
    return null;
  }

  return (
    <div>
      {!showForm ? (
        <button onClick={() => setShowForm(true)} type="button">
          {t("openDispute")}
        </button>
      ) : (
        <form onSubmit={sendDispute} style={{marginTop: "0.5rem"}}>
          <fieldset>
            <legend>{t("disputeType")}</legend>
            <label>
              <input
                type="radio"
                name="disputeType"
                value="canonicalization"
                checked={disputeType === "canonicalization"}
                onChange={() => setDisputeType("canonicalization")}
              />
              {t("badCanonicalization")}
            </label>
            <br />
            <label>
              <input
                type="radio"
                name="disputeType"
                value="cluster_assignment"
                checked={disputeType === "cluster_assignment"}
                onChange={() => setDisputeType("cluster_assignment")}
              />
              {t("wrongCluster")}
            </label>
          </fieldset>
          <div style={{marginTop: "0.5rem"}}>
            <label>
              {t("reason")}
              <br />
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
            </label>
          </div>
          <button type="submit" disabled={status === "loading"} style={{marginTop: "0.5rem"}}>
            {t("submit") ?? "Submit"}
          </button>
          {status === "error" && <p role="alert" style={{color: "red"}}>Error submitting dispute</p>}
        </form>
      )}
    </div>
  );
}
