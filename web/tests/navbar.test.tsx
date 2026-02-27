import React from "react";
import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {NavBar} from "../components/NavBar";

describe("NavBar", () => {
  it("renders navigation with all expected links", () => {
    render(<NavBar showOpsLink={false} />);
    const nav = screen.getByRole("navigation");
    expect(nav).toBeTruthy();

    const links = screen.getAllByRole("link");
    const hrefs = links.map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/en");
    expect(hrefs).toContain("/en/collective-concerns");
    expect(hrefs).toContain("/en/collective-concerns/community-votes");
    expect(hrefs).toContain("/en/my-activity");
    expect(hrefs).toContain("/en/collective-concerns/evidence");
    expect(hrefs).toContain("/en/sign-in");
  });

  it("renders signup button when not logged in", () => {
    render(<NavBar showOpsLink={false} />);
    const signInLinks = screen.getAllByText("Sign In");
    expect(signInLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("renders truncated email with full title when logged in", () => {
    render(<NavBar showOpsLink={false} userEmail="test@example.com" />);
    expect(screen.getAllByText("test@…").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTitle("test@example.com")).toBeTruthy();
    expect(screen.queryByText("Sign In")).toBeNull();
  });

  it("renders Home link text", () => {
    render(<NavBar showOpsLink={false} />);
    const homeLinks = screen.getAllByText("Home");
    expect(homeLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Collective Concerns link text", () => {
    render(<NavBar showOpsLink={false} />);
    expect(screen.getAllByText("Collective Concerns").length).toBeGreaterThanOrEqual(1);
  });

  it("renders My Activity link text", () => {
    render(<NavBar showOpsLink={false} />);
    expect(screen.getAllByText("My Activity").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Audit link text", () => {
    render(<NavBar showOpsLink={false} />);
    expect(screen.getAllByText("Audit").length).toBeGreaterThanOrEqual(1);
  });

  it("renders Ops link when flag is enabled", () => {
    render(<NavBar showOpsLink />);
    expect(screen.getAllByText("Ops").length).toBeGreaterThanOrEqual(1);
  });

  it("renders the language switcher buttons", () => {
    render(<NavBar showOpsLink={false} />);
    expect(screen.getAllByLabelText("English").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByLabelText("فارسی").length).toBeGreaterThanOrEqual(1);
  });
});
