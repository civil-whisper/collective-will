import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import AuditBundleDayPage from "../app/[locale]/collective-concerns/audit-bundles/[day]/page";
import {mockNotFound} from "./setup";

type FailedResponse = {ok: false; status: number};

function isFailedResponse(value: unknown): value is FailedResponse {
  return (
    typeof value === "object"
    && value !== null
    && "ok" in value
    && (value as {ok?: unknown}).ok === false
    && "status" in value
  );
}

function mockFetchSequence(...responses: Array<unknown | FailedResponse>) {
  const fn = vi.fn();
  for (const data of responses) {
    if (isFailedResponse(data)) {
      fn.mockResolvedValueOnce({
        ok: false,
        status: data.status,
        json: () => Promise.resolve({}),
      });
    } else {
      fn.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(data),
      });
    }
  }
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("AuditBundleDayPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    mockNotFound.mockClear();
  });

  it("renders audit snapshot detail page", async () => {
    mockFetchSequence({
      day_utc: "2026-03-15",
      entry_count: 12,
      daily_merkle_root: "root123",
      bundle_sha256: "bundle123",
      generated_at: "2026-03-15T12:00:00Z",
      visibility_policy_version: 1,
      event_catalog_version: "v1",
      timestamping: {
        status: "verified",
        verified_before: "2026-03-15T13:00:00Z",
        bitcoin_block_height: 123,
        ots_proof_present: true,
      },
      bundle_hash_matches_manifest: true,
      download_urls: {
        bundle: "/analytics/audit-bundles/2026-03-15/bundle",
        manifest: "/analytics/audit-bundles/2026-03-15/manifest",
        ots_proof: "/analytics/audit-bundles/2026-03-15/ots",
      },
    });
    const jsx = await AuditBundleDayPage({
      params: Promise.resolve({day: "2026-03-15"}),
    });
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Audit Snapshot Detail");
    expect(screen.getByText("Snapshot details")).toBeTruthy();
    expect(screen.getByText("bundle123")).toBeTruthy();
    expect(screen.getByText("root123")).toBeTruthy();
    expect(screen.getByText("verified")).toBeTruthy();
    expect(screen.getByRole("link", {name: "Download bundle"})).toHaveAttribute(
      "href",
      "http://localhost:8000/analytics/audit-bundles/2026-03-15/bundle",
    );
    expect(screen.getByRole("link", {name: "Open verification guide"})).toHaveAttribute(
      "href",
      "/en/independent-verification",
    );
  });

  it("calls notFound when the snapshot is missing", async () => {
    mockFetchSequence({ok: false, status: 404});
    await expect(
      AuditBundleDayPage({
        params: Promise.resolve({day: "2026-03-15"}),
      }),
    ).rejects.toThrow("notFound");
    expect(mockNotFound).toHaveBeenCalledOnce();
  });
});
