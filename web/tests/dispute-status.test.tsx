import React from "react";
import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {DisputeStatus} from "../components/DisputeStatus";

describe("DisputeStatus", () => {
  it("shows open state", () => {
    render(<DisputeStatus status="open" />);
    expect(screen.getByText(/automated review/i)).toBeTruthy();
  });

  it("shows resolved state", () => {
    render(<DisputeStatus status="resolved" />);
    expect(screen.getByText(/resolved/i)).toBeTruthy();
  });

  it("shows resolved with resolution text", () => {
    render(<DisputeStatus status="resolved" resolution="Re-canonicalized" />);
    expect(screen.getByText(/Re-canonicalized/)).toBeTruthy();
  });

  it("renders nothing for none status", () => {
    const {container} = render(<DisputeStatus status="none" />);
    expect(container.innerHTML).toBe("");
  });
});
