import React from "react";

type Props = {
  status: "none" | "open" | "resolved";
  resolution?: string;
};

export function DisputeStatus({status, resolution}: Props) {
  if (status === "open") {
    return <span role="status">🔍 under automated review</span>;
  }
  if (status === "resolved") {
    return (
      <span role="status">
        ✓ resolved{resolution ? `: ${resolution}` : ""}
      </span>
    );
  }
  return null;
}
