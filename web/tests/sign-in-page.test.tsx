import React from "react";
import {render, screen, fireEvent} from "@testing-library/react";
import {afterEach, describe, expect, it, vi} from "vitest";

import SignInPage from "../app/[locale]/sign-in/page";

describe("SignInPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders heading, email input, and submit button", () => {
    render(<SignInPage />);
    expect(screen.getByRole("heading", {level: 1})).toHaveTextContent("Sign in");
    expect(screen.getByRole("textbox")).toBeTruthy();
    expect(screen.getByRole("button", {name: /send verification link/i})).toBeTruthy();
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

  it("submits email to subscribe endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({status: "pending_verification"}),
      }),
    );
    render(<SignInPage />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, {target: {value: "test@example.com"}});
    fireEvent.submit(screen.getByRole("button", {name: /send verification link/i}).closest("form")!);

    await screen.findByText(/check your email/i);
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/auth/subscribe",
      expect.objectContaining({
        method: "POST",
        cache: "no-store",
      }),
    );
    const [, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({
      email: "test@example.com",
      locale: "en",
      messaging_account_ref: expect.stringMatching(/^web-/),
    });
  });
});
