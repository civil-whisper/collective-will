export type ReceiptStatus = "recorded" | "published" | "timestamped" | "verified" | "failed";

export type ReceiptEntry = {
  id: number;
  timestamp: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  hash: string;
  prev_hash: string;
  receipt_token: string;
};

export type ReceiptListResponse = {
  total: number;
  page: number;
  per_page: number;
  entries: ReceiptEntry[];
};

export type ReceiptVerification = {
  status: ReceiptStatus;
  receipt_valid: boolean;
  entry_found: boolean;
  bundle_day: string;
  included_in_public_bundle: boolean;
  bundle_hash_matches_manifest: boolean;
  ots_proof_present: boolean;
  ots_verified: boolean;
  verified_before: string | null;
  download_urls: {
    bundle: string | null;
    manifest: string | null;
    ots_proof: string | null;
  };
};

export function receiptBadgeVariant(status: ReceiptStatus): "success" | "warning" | "error" | "info" | "neutral" {
  switch (status) {
    case "recorded":
      return "info";
    case "published":
    case "timestamped":
    case "verified":
      return "success";
    case "failed":
      return "error";
  }
}

export function reachedReceiptStates(status: ReceiptStatus): ReceiptStatus[] {
  switch (status) {
    case "recorded":
      return ["recorded"];
    case "published":
      return ["recorded", "published"];
    case "timestamped":
      return ["recorded", "published", "timestamped"];
    case "verified":
      return ["recorded", "published", "timestamped", "verified"];
    case "failed":
      return ["recorded", "failed"];
  }
}

export function formatReceiptTimestamp(isoTimestamp: string, locale: string): string {
  return new Date(isoTimestamp).toLocaleString(locale === "fa" ? "fa-IR" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
