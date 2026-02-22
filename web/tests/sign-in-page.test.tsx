import React from "react";
import {render, screen, fireEvent} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";

const mockSignIn = vi.hoisted(() => vi.fn());
vi.mock("next-auth/react", () => ({
  signIn: mockSignIn,
}));

import SignInPage from "../app/[locale]/sign-in/page";

describe("SignInPage", () => {
  it("renders heading, email input, and submit button", () => {
    render(<SignInPage />);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Sign in");
    expect(screen.getByRole("textbox")).toBeTruthy();
    expect(screen.getByRole("button", {name: /continue/i})).toBeTruthy();
  });

  it("has a required email input", () => {
    render(<SignInPage />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    expect(input.type).toBe("email");
    expect(input.required).toBe(true);
  });

  it("updates email state on input change", () => {
    render(<SignInPage />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.change(input, {target: {value: "user@example.com"}});
    expect(input.value).toBe("user@example.com");
  });

  it("calls signIn with credentials provider on form submit", () => {
    mockSignIn.mockClear();
    render(<SignInPage />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, {target: {value: "test@example.com"}});
    fireEvent.submit(screen.getByRole("button", {name: /continue/i}).closest("form")!);

    expect(mockSignIn).toHaveBeenCalledWith("credentials", {
      email: "test@example.com",
      callbackUrl: "/en/dashboard",
    });
  });

  it("calls signIn with empty email if not filled in", () => {
    mockSignIn.mockClear();
    render(<SignInPage />);
    fireEvent.submit(screen.getByRole("button", {name: /continue/i}).closest("form")!);

    expect(mockSignIn).toHaveBeenCalledWith("credentials", {
      email: "",
      callbackUrl: "/en/dashboard",
    });
  });
});
