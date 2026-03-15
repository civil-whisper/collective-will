import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

vi.mock("../lib/backend-auth", () => ({
  getBackendAccessToken: vi.fn(async () => "test-access-token"),
  buildBearerHeaders: vi.fn((token: string) => ({Authorization: `Bearer ${token}`})),
}));

import DashboardPage from "../app/[locale]/my-activity/page";

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

function mockFetchError() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
  );
}

describe("DashboardPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading and summary cards", async () => {
    mockFetchSequence([], [], {entries: []});
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("My Activity");
    expect(screen.getByText(/Total Submissions/)).toBeTruthy();
    expect(screen.getByText(/Total Votes/)).toBeTruthy();
    expect(screen.getByText(/Total Receipts/)).toBeTruthy();
  });

  it("shows empty state messages when no data", async () => {
    mockFetchSequence([], [], {entries: []});
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText("You haven't submitted any concerns yet.")).toBeTruthy();
    expect(screen.getByText("You haven't voted yet.")).toBeTruthy();
    expect(screen.getByText("You do not have any receipt-eligible actions yet.")).toBeTruthy();
  });

  it("displays submissions with raw text and status", async () => {
    mockFetchSequence(
      [{id: "s1", raw_text: "Fix the economy", status: "processed", hash: "abc"}],
      [],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText("Fix the economy")).toBeTruthy();
    expect(screen.getByText(/processed/)).toBeTruthy();
  });

  it("shows Processing for pending submissions", async () => {
    mockFetchSequence(
      [{id: "s1", raw_text: "My concern", status: "pending", hash: "abc"}],
      [],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText(/Processing/)).toBeTruthy();
  });

  it("displays candidate info when present", async () => {
    mockFetchSequence(
      [
        {
          id: "s1",
          raw_text: "Test",
          status: "processed",
          hash: "abc",
          candidate: {
            title: "Economic Reform",
            summary: "Restructure fiscal policy",
            policy_topic: "fiscal-policy",
            confidence: 0.85,
          },
        },
      ],
      [],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText(/Economic Reform/)).toBeTruthy();
    expect(screen.getByText(/Restructure fiscal policy/)).toBeTruthy();
    expect(screen.getAllByText(/fiscal policy/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/85%/)).toBeTruthy();
  });

  it("displays cluster link when present", async () => {
    mockFetchSequence(
      [
        {
          id: "s1",
          raw_text: "Test",
          status: "processed",
          hash: "abc",
          cluster: {id: "c-42", summary: "Fiscal cluster", approval_count: 10},
        },
      ],
      [],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    const link = screen.getByRole("link", {name: /Fiscal cluster/});
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toBe("/en/collective-concerns/clusters/c-42");
  });

  it("shows DisputeStatus for submissions with open dispute", async () => {
    mockFetchSequence(
      [{id: "s1", raw_text: "Test", status: "processed", hash: "abc", dispute_status: "open"}],
      [],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText(/automated review/i)).toBeTruthy();
  });

  it("shows DisputeStatus for submissions with resolved dispute", async () => {
    mockFetchSequence(
      [{id: "s1", raw_text: "Test", status: "processed", hash: "abc", dispute_status: "resolved"}],
      [],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText(/resolved/i)).toBeTruthy();
  });

  it("shows DisputeButton for processed submissions without dispute", async () => {
    mockFetchSequence(
      [{id: "s1", raw_text: "Test", status: "processed", hash: "abc"}],
      [],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByRole("button", {name: /open dispute/i})).toBeTruthy();
  });

  it("does not show DisputeButton for pending submissions", async () => {
    mockFetchSequence(
      [{id: "s1", raw_text: "Test", status: "pending", hash: "abc"}],
      [],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.queryByRole("button", {name: /open dispute/i})).toBeNull();
  });

  it("displays votes with cycle id", async () => {
    mockFetchSequence(
      [],
      [{id: "v1", cycle_id: "cycle-99"}],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText("cycle-99")).toBeTruthy();
  });

  it("shows correct counts in summary cards", async () => {
    mockFetchSequence(
      [
        {id: "s1", raw_text: "A", status: "processed", hash: "a"},
        {id: "s2", raw_text: "B", status: "pending", hash: "b"},
      ],
      [{id: "v1", cycle_id: "c1"}],
      {entries: []},
    );
    const jsx = await DashboardPage();
    render(jsx);
    const html = document.body.innerHTML;
    expect(html).toContain(">2<");
    expect(html).toContain(">1<");
  });

  it("handles API failure gracefully", async () => {
    mockFetchError();
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText("You haven't submitted any concerns yet.")).toBeTruthy();
    expect(screen.getByText("You haven't voted yet.")).toBeTruthy();
  });

  it("renders receipt cards with verification link and status chips", async () => {
    mockFetchSequence(
      [],
      [],
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
        status: "published",
        receipt_valid: true,
        entry_found: true,
        bundle_day: "2026-03-15",
        included_in_public_bundle: true,
        bundle_hash_matches_manifest: true,
        ots_proof_present: false,
        ots_verified: false,
        verified_before: null,
        download_urls: {bundle: null, manifest: null, ots_proof: null},
      },
    );
    const jsx = await DashboardPage();
    render(jsx);
    expect(screen.getByText("Receipts")).toBeTruthy();
    expect(screen.getByText("Policy endorsed")).toBeTruthy();
    expect(screen.getByText("Recorded")).toBeTruthy();
    expect(screen.getByText("Published")).toBeTruthy();
    expect(screen.getByText("Timestamped")).toBeTruthy();
    const link = screen.getByRole("link", {name: "Verify this receipt"});
    expect(link.getAttribute("href")).toBe("/en/my-activity/receipts/receipt-hash-1");
  });
});
