// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm } from "./LoginForm";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  unsubscribe: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: mocks.unsubscribe } },
      })),
      signInWithPassword: mocks.signInWithPassword,
      signUp: mocks.signUp,
      resetPasswordForEmail: mocks.resetPasswordForEmail,
    },
  }),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

async function openSignUp() {
  await userEvent.click(screen.getByRole("button", { name: "Sign up" }));
}

beforeEach(() => {
  window.history.replaceState({}, "", "/login");
  mocks.replace.mockReset();
  mocks.signInWithPassword.mockReset();
  mocks.signUp.mockReset();
  mocks.resetPasswordForEmail.mockReset();
  mocks.unsubscribe.mockReset();
  mocks.signInWithPassword.mockResolvedValue({ error: null });
  mocks.signUp.mockResolvedValue({ data: { session: null }, error: null });
  mocks.resetPasswordForEmail.mockResolvedValue({ error: null });
});

afterEach(() => {
  cleanup();
});

describe("LoginForm", () => {
  it("blocks signup and explains when the passwords do not match", async () => {
    render(<LoginForm />);
    await openSignUp();

    await userEvent.type(screen.getByLabelText("Email"), "reader@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "long-enough");
    await userEvent.type(screen.getByLabelText("Confirm password"), "different");

    expect(screen.getByText("Passwords do not match.")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Create account" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(mocks.signUp).not.toHaveBeenCalled();
  });

  it("does not impose the signup minimum on an existing user's login", async () => {
    render(<LoginForm />);

    const passwordInput = screen.getByLabelText("Password") as HTMLInputElement;
    expect(passwordInput.minLength).toBe(-1);

    await userEvent.type(screen.getByLabelText("Email"), "reader@example.com");
    await userEvent.type(passwordInput, "short7");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(mocks.signInWithPassword).toHaveBeenCalledWith({
        email: "reader@example.com",
        password: "short7",
      });
    });
  });

  it("requires eight characters when creating an account", async () => {
    render(<LoginForm />);
    await openSignUp();

    expect((screen.getByLabelText("Password") as HTMLInputElement).minLength).toBe(8);
    expect(
      (screen.getByLabelText("Confirm password") as HTMLInputElement).minLength,
    ).toBe(8);
  });

  it("shows a callback failure once and removes it from the URL", () => {
    window.history.replaceState({}, "", "/login?error=auth");

    render(<LoginForm />);

    expect(
      screen.getByText(
        "This confirmation link is invalid or has expired. Please sign up again or request a new link.",
      ),
    ).toBeTruthy();
    expect(window.location.pathname).toBe("/login");
    expect(window.location.search).toBe("");
  });

  it("recovers from a thrown authentication error", async () => {
    mocks.signInWithPassword.mockRejectedValue(new Error("network unavailable"));
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText("Email"), "reader@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByText(
        "We couldn't reach the authentication service. Please try again.",
      ),
    ).toBeTruthy();
    expect((screen.getByRole("button", { name: "Sign in" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("locks inputs and mode controls while a request is active", async () => {
    const pending = deferred<{ error: null }>();
    mocks.signInWithPassword.mockReturnValue(pending.promise);
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText("Email"), "reader@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect((screen.getByLabelText("Email") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Password") as HTMLInputElement).disabled).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Forgot your password?" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect((screen.getByRole("button", { name: "Sign up" }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    pending.resolve({ error: null });
    await waitFor(() => {
      expect((screen.getByLabelText("Email") as HTMLInputElement).disabled).toBe(false);
    });
  });
});
