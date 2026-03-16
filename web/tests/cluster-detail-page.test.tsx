import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import ClusterDetailPage from "../app/[locale]/collective-concerns/clusters/[id]/page";

function mockFetchWith(data: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
    }),
  );
}

const FULL_CLUSTER = {
  id: "c1",
  summary: "Economic reform proposals",
  policy_topic: "fiscal-policy",
  policy_key: "fiscal-policy-001",
  member_count: 12,
  approval_count: 8,
  endorsement_count: 5,
  ballot_stage: "needs-refinement",
  readiness_counts: {"ballot-ready": 1, "needs-refinement": 1, "discussion-only": 0},
  refinement_draft: "The government should expand bus routes and service frequency in underserved areas.",
  refinement_draft_fa: "دولت باید مسیرها و تعداد سرویس اتوبوس را در مناطق کم‌برخوردار افزایش دهد.",
  refinement_confidence: 0.82,
  refinement_requires_clarification: false,
  refinement_notes: "Multiple submissions point toward a concrete transit expansion proposal.",
  candidates: [
    {
      id: "p1",
      submission_id: "s1",
      title: "Tax Reform",
      summary: "Simplify tax code",
      policy_topic: "fiscal-policy",
      policy_key: "fiscal-policy-001",
      actor_scope: "public-governance",
      action_mechanism: "governance-design",
      target_scope: "public-governance",
      ballot_readiness: "ballot-ready",
      ballot_readiness_reason: "Concrete enough for a ballot proposition.",
      confidence: 0.92,
    },
    {
      id: "p2",
      submission_id: "s2",
      title: "Budget Cuts",
      summary: "Reduce spending",
      policy_topic: "fiscal-policy",
      policy_key: "fiscal-policy-002",
      actor_scope: "public-governance",
      action_mechanism: "governance-design",
      target_scope: "public-governance",
      ballot_readiness: "needs-refinement",
      ballot_readiness_reason: "Still too broad.",
      confidence: 0.78,
    },
  ],
};

function makeParams(id: string): Promise<{id: string}> {
  return Promise.resolve({id});
}

describe("ClusterDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows not found message when cluster doesn't exist", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 404, json: () => Promise.resolve({})}),
    );
    const jsx = await ClusterDetailPage({params: makeParams("nonexistent")});
    render(jsx);
    expect(screen.getByText("No grouped concerns yet.")).toBeTruthy();
  });

  it("renders policy topic as heading and summary as body text", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("fiscal policy");
    expect(screen.getByText("Economic reform proposals")).toBeTruthy();
  });

  it("displays submissions, endorsements, and total support", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getAllByText("Submissions").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Endorsements")).toBeTruthy();
    expect(screen.getByText("Total Support")).toBeTruthy();
    expect(screen.getAllByText(/12/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/5/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/17/).length).toBeGreaterThanOrEqual(1);
  });

  it("lists all policy candidates", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getByText("Tax Reform")).toBeTruthy();
    expect(screen.getByText("Budget Cuts")).toBeTruthy();
  });

  it("shows candidate summaries and confidence", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getByText(/Simplify tax code/)).toBeTruthy();
    expect(screen.getByText(/92%/)).toBeTruthy();
    expect(screen.getByText(/Reduce spending/)).toBeTruthy();
    expect(screen.getByText(/78%/)).toBeTruthy();
  });

  it("shows stage and semantic metadata", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getAllByText("Needs refinement").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Actor:/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Mechanism:/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/View submission history/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Proposition Draft")).toBeTruthy();
    expect(screen.getByText(/bus routes and service frequency/)).toBeTruthy();
  });

  it("fetches from the correct API endpoint using params id", async () => {
    mockFetchWith(FULL_CLUSTER);
    await ClusterDetailPage({params: makeParams("my-cluster-id")});
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/analytics/clusters/my-cluster-id");
  });
});
