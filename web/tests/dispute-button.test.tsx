import React, {act} from "react";
import {render, screen, fireEvent, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

import {DisputeButton} from "../components/DisputeButton";

describe("DisputeButton", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the open dispute button", () => {
    render(<DisputeButton submissionId="sub-1" />);
    expect(screen.getByRole("button", {name: /open dispute/i})).toBeTruthy();
  });

  it("renders nothing when disabled", () => {
    const {container} = render(<DisputeButton submissionId="sub-1" disabled />);
    expect(container.innerHTML).toBe("");
  });

  it("opens the form when button is clicked", () => {
    render(<DisputeButton submissionId="sub-1" />);
    fireEvent.click(screen.getByRole("button", {name: /open dispute/i}));
    expect(screen.getByRole("group")).toBeTruthy();
    expect(screen.getByRole("radio", {name: /misunderstood/i})).toBeTruthy();
    expect(screen.getByRole("radio", {name: /wrong group/i})).toBeTruthy();
  });

  it("has canonicalization selected by default", () => {
    render(<DisputeButton submissionId="sub-1" />);
    fireEvent.click(screen.getByRole("button", {name: /open dispute/i}));
    const canonRadio = screen.getByRole("radio", {name: /misunderstood/i}) as HTMLInputElement;
    expect(canonRadio.checked).toBe(true);
  });

  it("allows switching dispute type to cluster_assignment", () => {
    render(<DisputeButton submissionId="sub-1" />);
    fireEvent.click(screen.getByRole("button", {name: /open dispute/i}));
    const clusterRadio = screen.getByRole("radio", {name: /wrong group/i}) as HTMLInputElement;
    fireEvent.click(clusterRadio);
    expect(clusterRadio.checked).toBe(true);
  });

  it("shows under review after successful submit", async () => {
    render(<DisputeButton submissionId="sub-1" />);
    fireEvent.click(screen.getByRole("button", {name: /open dispute/i}));
    fireEvent.submit(screen.getByRole("button", {name: /submit/i}).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText(/under automated review/i)).toBeTruthy();
    });
  });

  it("shows error on API failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    render(<DisputeButton submissionId="sub-1" />);
    fireEvent.click(screen.getByRole("button", {name: /open dispute/i}));
    fireEvent.submit(screen.getByRole("button", {name: /submit/i}).closest("form")!);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    expect(screen.getByRole("alert").textContent).toContain("Error");
  });

  it("sends correct payload to API", async () => {
    render(<DisputeButton submissionId="sub-42" />);
    fireEvent.click(screen.getByRole("button", {name: /open dispute/i}));

    const clusterRadio = screen.getByRole("radio", {name: /wrong group/i});
    fireEvent.click(clusterRadio);

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, {target: {value: "Wrong cluster"}});

    fireEvent.submit(screen.getByRole("button", {name: /submit/i}).closest("form")!);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });

    const [url, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/api/user/dashboard/disputes/sub-42");
    const body = JSON.parse(options.body);
    expect(body.dispute_type).toBe("cluster_assignment");
    expect(body.reason).toBe("Wrong cluster");
  });

  it("disables submit button while loading", async () => {
    let resolveFetch!: (value: unknown) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
      ),
    );
    render(<DisputeButton submissionId="sub-1" />);
    fireEvent.click(screen.getByRole("button", {name: /open dispute/i}));
    fireEvent.submit(screen.getByRole("button", {name: /submit/i}).closest("form")!);

    await waitFor(() => {
      const submitBtn = screen.getByRole("button", {name: /submit/i});
      expect(submitBtn).toBeDisabled();
    });

    await act(async () => {
      resolveFetch({ok: true, json: () => Promise.resolve({})});
    });
  });
});
