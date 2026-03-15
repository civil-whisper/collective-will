import React from "react";
import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import IndependentVerificationPage from "../app/[locale]/independent-verification/page";

describe("IndependentVerificationPage", () => {
  it("renders the public verification guide", async () => {
    const jsx = await IndependentVerificationPage();
    render(jsx);

    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Independent Verification Guide");
    expect(screen.getByText("Quick path")).toBeTruthy();
    expect(screen.getByText("Journalist and researcher path")).toBeTruthy();
    expect(screen.getByText("Optional command-line path")).toBeTruthy();
    expect(screen.getByRole("link", {name: "View daily audit snapshots"})).toHaveAttribute(
      "href",
      "/en/collective-concerns/audit-bundles",
    );
  });
});
