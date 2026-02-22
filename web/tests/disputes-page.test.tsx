import React from "react";
import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import DisputesPage from "../app/[locale]/dashboard/disputes/page";

describe("DisputesPage", () => {
  it("renders heading", () => {
    render(<DisputesPage />);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Disputes");
  });

  it("renders DisputeStatus with open state", () => {
    render(<DisputesPage />);
    expect(screen.getByText(/automated review/i)).toBeTruthy();
  });
});
