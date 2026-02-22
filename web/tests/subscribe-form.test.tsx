import React, {act} from "react";
import {render, screen, fireEvent, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, describe, expect, it, vi} from "vitest";

import {SubscribeForm} from "../components/SubscribeForm";

describe("SubscribeForm", () => {
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

  it("renders email input and submit button", () => {
    render(<SubscribeForm />);
    expect(screen.getByRole("textbox")).toBeTruthy();
    expect(screen.getByRole("button")).toBeTruthy();
  });

  it("shows success message after submission", async () => {
    render(<SubscribeForm />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, {target: {value: "user@example.com"}});
    fireEvent.submit(screen.getByRole("button").closest("form")!);

    await waitFor(() => {
      expect(screen.getByRole("status")).toBeTruthy();
    });
    expect(screen.getByRole("status").textContent).toContain("Verification link sent");
  });

  it("shows error message when API fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ok: false, status: 500, json: () => Promise.resolve({})}),
    );
    render(<SubscribeForm />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, {target: {value: "user@example.com"}});
    fireEvent.submit(screen.getByRole("button").closest("form")!);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
    expect(screen.getByRole("alert").textContent).toContain("Something went wrong");
  });

  it("disables button while loading", async () => {
    let resolveFetch!: (value: unknown) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
      ),
    );
    render(<SubscribeForm />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, {target: {value: "user@example.com"}});
    fireEvent.submit(screen.getByRole("button").closest("form")!);

    await waitFor(() => {
      expect(screen.getByRole("button")).toBeDisabled();
    });
    expect(screen.getByRole("button").textContent).toContain("Loading");

    await act(async () => {
      resolveFetch({ok: true, json: () => Promise.resolve({})});
    });
  });

  it("sends correct payload to API", async () => {
    render(<SubscribeForm />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, {target: {value: "test@example.com"}});
    fireEvent.submit(screen.getByRole("button").closest("form")!);

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
    const [url, options] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/auth/subscribe");
    const body = JSON.parse(options.body);
    expect(body.email).toBe("test@example.com");
    expect(body.locale).toBe("en");
    expect(body.messaging_account_ref).toMatch(/^web-[0-9a-f-]{36}$/);
  });

  it("generates unique messaging_account_ref per submission", async () => {
    render(<SubscribeForm />);
    const input = screen.getByRole("textbox");

    fireEvent.change(input, {target: {value: "a@example.com"}});
    fireEvent.submit(screen.getByRole("button").closest("form")!);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));

    fireEvent.change(input, {target: {value: "b@example.com"}});
    fireEvent.submit(screen.getByRole("button").closest("form")!);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));

    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls;
    const ref1 = JSON.parse(calls[0][1].body).messaging_account_ref;
    const ref2 = JSON.parse(calls[1][1].body).messaging_account_ref;
    expect(ref1).not.toBe(ref2);
  });
});
