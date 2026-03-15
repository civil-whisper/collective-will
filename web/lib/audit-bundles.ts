import {resolveServerApiBase} from "@/lib/auth-config";

export type AuditBundleListItem = {
  day_utc: string;
  entry_count: number | null;
  daily_merkle_root: string | null;
  timestamping_status: string | null;
  ots_proof_path: string | null;
  download_urls: {
    bundle: string;
    manifest: string;
    ots_proof: string;
  };
  detail_url: string;
};

export type AuditBundleListResponse = {
  schema_version: number;
  updated_at: string | null;
  days: AuditBundleListItem[];
};

export type AuditBundleDayResponse = {
  day_utc: string;
  entry_count: number | null;
  daily_merkle_root: string | null;
  bundle_sha256: string | null;
  generated_at: string | null;
  visibility_policy_version: number | null;
  event_catalog_version: string | null;
  timestamping: {
    status: string | null;
    verified_before: string | null;
    bitcoin_block_height: number | null;
    ots_proof_present: boolean;
  };
  bundle_hash_matches_manifest: boolean;
  download_urls: {
    bundle: string;
    manifest: string;
    ots_proof: string;
  };
};

export function absoluteApiUrl(url: string | null): string | null {
  if (!url) return null;
  if (/^https?:\/\//i.test(url)) return url;
  return `${resolveServerApiBase()}${url.startsWith("/") ? url : `/${url}`}`;
}

export function formatAuditDate(day: string, locale: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(locale === "fa" ? "fa-IR" : "en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function timestampStatusVariant(status: string | null): "success" | "warning" | "error" | "info" | "neutral" {
  switch (status) {
    case "verified":
      return "success";
    case "stamped":
    case "pending":
      return "info";
    case "failed":
      return "error";
    default:
      return "neutral";
  }
}
