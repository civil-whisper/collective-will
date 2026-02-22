import React from "react";
import {render, screen} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import ClusterDetailPage from "../app/[locale]/analytics/clusters/[id]/page";

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
  summary_en: "Economic reform proposals (EN)",
  domain: "economy",
  member_count: 12,
  approval_count: 8,
  variance_flag: false,
  grouping_rationale: "Grouped by fiscal policy similarity",
  candidates: [
    {id: "p1", title: "Tax Reform", summary: "Simplify tax code", domain: "economy", confidence: 0.92},
    {id: "p2", title: "Budget Cuts", summary: "Reduce spending", domain: "economy", confidence: 0.78},
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
    expect(screen.getByText("No clusters have been created yet.")).toBeTruthy();
  });

  it("renders cluster summary as heading", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Economic reform proposals");
  });

  it("displays English summary when present", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getByText("Economic reform proposals (EN)")).toBeTruthy();
  });

  it("does not display English summary when absent", async () => {
    mockFetchWith({...FULL_CLUSTER, summary_en: undefined});
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.queryByText(/\(EN\)/)).toBeNull();
  });

  it("displays grouping rationale when present", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getByText("Grouped by fiscal policy similarity")).toBeTruthy();
  });

  it("does not display grouping rationale when absent", async () => {
    mockFetchWith({...FULL_CLUSTER, grouping_rationale: undefined});
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.queryByText(/Grouped by/)).toBeNull();
  });

  it("displays domain, member count, and approval count", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getAllByText(/Domain: economy/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Member Count: 12/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Approval Count: 8/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows variance flag when set", async () => {
    mockFetchWith({...FULL_CLUSTER, variance_flag: true});
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getByText(/Unstable/)).toBeTruthy();
  });

  it("does not show variance flag when not set", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.queryByText(/Unstable/)).toBeNull();
  });

  it("lists all policy candidates", async () => {
    mockFetchWith(FULL_CLUSTER);
    const jsx = await ClusterDetailPage({params: makeParams("c1")});
    render(jsx);
    expect(screen.getAllByRole("listitem").length).toBe(2);
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

  it("fetches from the correct API endpoint using params id", async () => {
    mockFetchWith(FULL_CLUSTER);
    await ClusterDetailPage({params: makeParams("my-cluster-id")});
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/analytics/clusters/my-cluster-id");
  });
});
