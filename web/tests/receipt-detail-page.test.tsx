import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

vi.mock("../lib/backend-auth", () => ({
  getBackendAccessToken: vi.fn(async () => "test-access-token"),
  buildBearerHeaders: vi.fn((token: string) => ({Authorization: `Bearer ${token}`})),
}));

import ReceiptVerificationPage from "../app/[locale]/my-activity/receipts/[entryHash]/page";
import {mockNotFound} from "./setup";

function mockFetchSequence(...responses: unknown[]) {
  const fn = vi.fn();
  for (const data of responses) {
    fn.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(data),
    });
  }
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("ReceiptVerificationPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    mockNotFound.mockClear();
  });

  it("renders receipt verification details", async () => {
    mockFetchSequence(
      {
        entries: [
          {
            id: 1,
            timestamp: "2026-03-15T10:00:00Z",
            event_type: "policy_endorsed",
            entity_type: "policy_endorsement",
            entity_id: "cluster-1",
            payload: {cluster_id: "cluster-1"},
            hash: "receipt-hash-1",
            prev_hash: "prev",
            receipt_token: "token-1",
          },
        ],
      },
      {
        status: "verified",
        receipt_valid: true,
        entry_found: true,
        bundle_day: "2026-03-15",
        included_in_public_bundle: true,
        bundle_hash_matches_manifest: true,
        ots_proof_present: true,
        ots_verified: true,
        verified_before: "2026-03-15T12:00:00Z",
        download_urls: {
          bundle: "/audit/2026-03-15/audit-2026-03-15.jsonl.gz",
          manifest: "/audit/2026-03-15/manifest-2026-03-15.json",
          ots_proof: "/audit/2026-03-15/audit-2026-03-15.ots",
        },
      },
    );
    const jsx = await ReceiptVerificationPage({
      params: Promise.resolve({entryHash: "receipt-hash-1"}),
    });
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Receipt Verification");
    expect(screen.getByText("What happened")).toBeTruthy();
    expect(screen.getByText("Verification status")).toBeTruthy();
    expect(screen.getByText("Verified")).toBeTruthy();
    expect(screen.getByText("What this proves")).toBeTruthy();
    expect(screen.getByText("Downloads for independent verification")).toBeTruthy();
    expect(screen.getByText("Entry hash")).toBeTruthy();
    expect(screen.getByText("receipt-hash-1")).toBeTruthy();
    expect(screen.getByText("token-1")).toBeTruthy();
    expect(screen.getByRole("link", {name: "Open the public verification guide"})).toHaveAttribute(
      "href",
      "/en/independent-verification",
    );
  });

  it("shows unavailable proof files when downloads are not ready", async () => {
    mockFetchSequence(
      {
        entries: [
          {
            id: 1,
            timestamp: "2026-03-15T10:00:00Z",
            event_type: "vote_cast",
            entity_type: "vote",
            entity_id: "vote-1",
            payload: {approved_cluster_ids: ["cluster-1", "cluster-2"]},
            hash: "receipt-hash-2",
            prev_hash: "prev",
            receipt_token: "token-2",
          },
        ],
      },
      {
        status: "recorded",
        receipt_valid: true,
        entry_found: true,
        bundle_day: "",
        included_in_public_bundle: false,
        bundle_hash_matches_manifest: false,
        ots_proof_present: false,
        ots_verified: false,
        verified_before: null,
        download_urls: {
          bundle: null,
          manifest: null,
          ots_proof: null,
        },
      },
    );
    const jsx = await ReceiptVerificationPage({
      params: Promise.resolve({entryHash: "receipt-hash-2"}),
    });
    render(jsx);
    expect(screen.getAllByText("Not available yet").length).toBe(3);
    expect(screen.getByText("Recorded")).toBeTruthy();
  });

  it("calls notFound when the receipt is missing", async () => {
    mockFetchSequence({entries: []});
    await expect(
      ReceiptVerificationPage({
        params: Promise.resolve({entryHash: "missing"}),
      }),
    ).rejects.toThrow("notFound");
    expect(mockNotFound).toHaveBeenCalledOnce();
  });
});
