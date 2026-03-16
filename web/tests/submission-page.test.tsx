import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import SubmissionPage from "../app/[locale]/submission/[id]/page";

function mockFetchWith(data: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
    }),
  );
}

const HISTORY = {
  submission_id: "s1",
  raw_text: "Workers should strike to weaken the regime economically",
  status: "canonicalized",
  candidate_ids: ["c1"],
  candidate: {
    id: "c1",
    submission_id: "s1",
    title: "Domestic Economic Strike",
    summary: "Calls for domestic strike action to economically weaken the regime.",
    policy_topic: "economic-resistance",
    policy_key: "domestic-economic-strike",
    actor_scope: "domestic-citizens",
    action_mechanism: "labor-strike",
    target_scope: "iranian-regime",
    ballot_readiness: "ballot-ready",
    ballot_readiness_reason: "This is a concrete tactic.",
    confidence: 0.84,
    raw_text: "Workers should strike to weaken the regime economically",
    language: "en",
  },
  location: {status: "clustered", cluster_id: "cluster-1"},
  entries: [
    {
      id: 1,
      timestamp: "2026-03-15T12:00:00Z",
      event_type: "candidate_classified",
      entity_type: "candidate",
      entity_id: "c1",
      payload: {policy_key: "domestic-economic-strike", ballot_readiness: "ballot-ready"},
    },
  ],
};

function makeParams(id: string): Promise<{id: string}> {
  return Promise.resolve({id});
}

describe("SubmissionPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders current classification and history", async () => {
    mockFetchWith(HISTORY);
    const jsx = await SubmissionPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Domestic Economic Strike");
    expect(screen.getByText("Ballot-ready")).toBeTruthy();
    expect(screen.getByText(/labor-strike/)).toBeTruthy();
    expect(screen.getByText("Pipeline History")).toBeTruthy();
    expect(screen.getByText(/candidate classified/)).toBeTruthy();
  });

  it("shows not found state on API failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 404, json: () => Promise.resolve({})}),
    );
    const jsx = await SubmissionPage({params: makeParams("missing")});
    render(jsx);
    expect(screen.getByText("Submission not found")).toBeTruthy();
  });
});
