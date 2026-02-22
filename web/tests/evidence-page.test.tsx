import React, {act} from "react";
import {render, screen, fireEvent, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

import EvidencePage from "../app/[locale]/analytics/evidence/page";

const SAMPLE_ENTRIES = [
  {
    timestamp: "2026-02-20T10:00:00.000Z",
    event_type: "submission_received",
    entity_type: "submission",
    entity_id: "entity-aaa",
    payload: {text: "hello"},
    hash: "aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666",
    prev_hash: "genesis",
  },
  {
    timestamp: "2026-02-20T10:01:00.000Z",
    event_type: "candidate_created",
    entity_type: "candidate",
    entity_id: "entity-bbb",
    payload: {title: "Policy X"},
    hash: "bbbb2222cccc3333dddd4444eeee5555ffff6666aaaa1111",
    prev_hash: "aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666",
  },
];

function mockFetchWith(entries: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(entries),
    }),
  );
}

describe("EvidencePage", () => {
  beforeEach(() => {
    mockFetchWith(SAMPLE_ENTRIES);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading and verify button", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Evidence Chain");
    expect(screen.getByRole("button", {name: /verify chain/i})).toBeTruthy();
  });

  it("fetches and displays entries on mount", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/submission_received/)).toBeTruthy();
      expect(screen.getByText(/candidate_created/)).toBeTruthy();
    });
    expect(screen.getByText("2")).toBeTruthy();
  });

  it("shows truncated hash for each entry", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/aaaa1111bbbb2222cccc/)).toBeTruthy();
      expect(screen.getByText(/bbbb2222cccc3333dddd/)).toBeTruthy();
    });
  });

  it("filters entries by search term on event_type", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/submission_received/)).toBeTruthy();
    });

    const searchInput = screen.getByLabelText(/search/i);
    fireEvent.change(searchInput, {target: {value: "candidate_created"}});

    expect(screen.queryByText(/submission_received/)).toBeNull();
    expect(screen.getByText(/candidate_created/)).toBeTruthy();
  });

  it("filters entries by search term on entity_id", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getAllByText(/submission_received|candidate_created/).length).toBe(2);
    });

    const searchInput = screen.getByLabelText(/search/i);
    fireEvent.change(searchInput, {target: {value: "entity-bbb"}});

    expect(screen.getByText(/candidate_created/)).toBeTruthy();
    expect(screen.queryByText(/submission_received/)).toBeNull();
  });

  it("filters entries by search term on hash", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getAllByText(/submission_received|candidate_created/).length).toBe(2);
    });

    const searchInput = screen.getByLabelText(/search/i);
    fireEvent.change(searchInput, {target: {value: "aaaa1111bbbb2222cccc"}});

    expect(screen.getAllByText(/submission_received|candidate_created/).length).toBe(1);
  });

  it("shows all entries when search is cleared", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getAllByText(/submission_received|candidate_created/).length).toBe(2);
    });

    const searchInput = screen.getByLabelText(/search/i);
    fireEvent.change(searchInput, {target: {value: "entity-aaa"}});
    expect(screen.getAllByText(/submission_received/).length).toBe(1);

    fireEvent.change(searchInput, {target: {value: ""}});
    expect(screen.getAllByText(/submission_received|candidate_created/).length).toBe(2);
  });

  it("expands entry details on click", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/submission_received/)).toBeTruthy();
    });

    expect(screen.queryByText(/entity-aaa/)).toBeNull();

    const entryButton = screen.getAllByRole("button").find(
      (btn) => btn.textContent?.includes("submission_received"),
    )!;
    fireEvent.click(entryButton);

    expect(screen.getByText(/entity-aaa/)).toBeTruthy();
    expect(screen.getByText(/"text": "hello"/)).toBeTruthy();
  });

  it("collapses entry details on second click", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/submission_received/)).toBeTruthy();
    });

    const entryButton = screen.getAllByRole("button").find(
      (btn) => btn.textContent?.includes("submission_received"),
    )!;
    fireEvent.click(entryButton);
    expect(screen.getByText(/entity-aaa/)).toBeTruthy();

    fireEvent.click(entryButton);
    await waitFor(() => {
      const entityTexts = screen.queryAllByText(/Entity ID:/);
      const entityAaaVisible = entityTexts.some((el) => el.textContent?.includes("entity-aaa"));
      expect(entityAaaVisible).toBe(false);
    });
  });

  it("expands entry on Enter keypress", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/submission_received/)).toBeTruthy();
    });

    const entryButton = screen.getAllByRole("button").find(
      (btn) => btn.textContent?.includes("submission_received"),
    )!;
    fireEvent.keyDown(entryButton, {key: "Enter"});

    expect(screen.getByText(/entity-aaa/)).toBeTruthy();
  });

  it("has Previous button disabled on page 1", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    const prevBtn = screen.getByRole("button", {name: /previous/i});
    expect(prevBtn).toBeDisabled();
  });

  it("increments page on Next click and fetches again", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(1);
    });
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain("page=1");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {name: /next/i}));
    });

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(2);
    });
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[1][0]).toContain("page=2");
  });

  it("does not decrement page below 1", async () => {
    await act(async () => {
      render(<EvidencePage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {name: /previous/i}));
    });
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  it("shows chain valid after verify with valid data", async () => {
    const entry = {
      timestamp: "2026-02-20T10:00:00.000Z",
      event_type: "test_event",
      entity_type: "test",
      entity_id: "entity-0",
      payload: {index: 0},
      prev_hash: "genesis",
      hash: "",
    };
    const material = {
      entity_id: "entity-0",
      entity_type: "test",
      event_type: "test_event",
      payload: {index: 0},
      prev_hash: "genesis",
      timestamp: "2026-02-20T10:00:00.000Z",
    };
    const data = new TextEncoder().encode(JSON.stringify(material, Object.keys(material).sort()));
    const digest = await crypto.subtle.digest("SHA-256", data);
    entry.hash = Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

    mockFetchWith([entry]);

    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/test_event/)).toBeTruthy();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {name: /verify chain/i}));
    });

    await waitFor(() => {
      expect(screen.getByText(/Chain Valid/i)).toBeTruthy();
    });
  });

  it("shows chain invalid for tampered data", async () => {
    const entries = [
      {
        ...SAMPLE_ENTRIES[0],
        hash: "definitely_wrong_hash",
      },
    ];
    mockFetchWith(entries);

    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText(/submission_received/)).toBeTruthy();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {name: /verify chain/i}));
    });

    await waitFor(() => {
      expect(screen.getByText(/Chain Broken/i)).toBeTruthy();
    });
  });

  it("shows empty list when API fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    await act(async () => {
      render(<EvidencePage />);
    });
    await waitFor(() => {
      expect(screen.getByText("0")).toBeTruthy();
    });
  });
});
