import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import AuditBundlesPage from "../app/[locale]/collective-concerns/audit-bundles/page";

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

describe("AuditBundlesPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders audit snapshot cards", async () => {
    mockFetchSequence({
      schema_version: 1,
      updated_at: "2026-03-15T12:00:00Z",
      days: [
        {
          day_utc: "2026-03-15",
          entry_count: 12,
          daily_merkle_root: "root123",
          timestamping_status: "pending",
          ots_proof_path: "/audit/2026-03-15/audit-2026-03-15.ots",
          download_urls: {
            bundle: "/analytics/audit-bundles/2026-03-15/bundle",
            manifest: "/analytics/audit-bundles/2026-03-15/manifest",
            ots_proof: "/analytics/audit-bundles/2026-03-15/ots",
          },
          detail_url: "/analytics/audit-bundles/2026-03-15",
        },
      ],
    });
    const jsx = await AuditBundlesPage();
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Daily Audit Snapshots");
    expect(screen.getByText("12 public entries")).toBeTruthy();
    expect(screen.getByText(/Merkle root:/)).toBeTruthy();
    expect(screen.getByRole("link", {name: "View snapshot"})).toHaveAttribute(
      "href",
      "/en/collective-concerns/audit-bundles/2026-03-15",
    );
  });

  it("shows empty state when no snapshots are available", async () => {
    mockFetchSequence({
      schema_version: 1,
      updated_at: null,
      days: [],
    });
    const jsx = await AuditBundlesPage();
    render(jsx);
    expect(screen.getByText("No public audit snapshots are available yet.")).toBeTruthy();
  });
});
