// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GoogleCredentialResponse } from "@/lib/google-identity";

const mocks = vi.hoisted(() => ({
  clientId: "client-123",
  load: vi.fn(),
  initialize: vi.fn(),
  renderButton: vi.fn(),
  nonces: [] as { raw: string; hashed: string }[],
}));

vi.mock("@/lib/google-identity", () => ({
  get GOOGLE_CLIENT_ID() {
    return mocks.clientId;
  },
  loadGoogleIdentity: mocks.load,
  createNonce: async () => mocks.nonces.shift() ?? { raw: "raw-x", hashed: "hashed-x" },
}));

import { GoogleSignInButton } from "./GoogleSignInButton";

const fallback = <button type="button">Fallback Google</button>;

function lastCallback(): (response: GoogleCredentialResponse) => void {
  return mocks.initialize.mock.calls[mocks.initialize.mock.calls.length - 1][0].callback;
}

beforeEach(() => {
  mocks.clientId = "client-123";
  mocks.initialize.mockReset();
  mocks.renderButton.mockReset();
  mocks.load.mockReset();
  mocks.load.mockResolvedValue({ initialize: mocks.initialize, renderButton: mocks.renderButton });
  mocks.nonces = [
    { raw: "raw-1", hashed: "hashed-1" },
    { raw: "raw-2", hashed: "hashed-2" },
  ];
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
});

describe("GoogleSignInButton", () => {
  it("renders Google's button with the hashed nonce and dark styling", async () => {
    render(<GoogleSignInButton onCredential={vi.fn()} fallback={fallback} />);

    await waitFor(() => expect(mocks.renderButton).toHaveBeenCalled());
    expect(mocks.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ client_id: "client-123", nonce: "hashed-1", ux_mode: "popup" }),
    );
    expect(mocks.renderButton.mock.calls[0][1]).toMatchObject({ theme: "filled_black", text: "continue_with" });
    expect(screen.queryByText("Fallback Google")).toBeNull();
  });

  it("uses the outline style on the light theme", async () => {
    document.documentElement.dataset.theme = "light";
    render(<GoogleSignInButton onCredential={vi.fn()} fallback={fallback} />);

    await waitFor(() => expect(mocks.renderButton).toHaveBeenCalled());
    expect(mocks.renderButton.mock.calls[0][1].theme).toBe("outline");
  });

  it("passes the credential with the raw nonce, then re-arms with a fresh nonce", async () => {
    const onCredential = vi.fn();
    render(<GoogleSignInButton onCredential={onCredential} fallback={fallback} />);
    await waitFor(() => expect(mocks.initialize).toHaveBeenCalledTimes(1));

    lastCallback()({ credential: "id-token" });

    expect(onCredential).toHaveBeenCalledWith("id-token", "raw-1");
    await waitFor(() => expect(mocks.initialize).toHaveBeenCalledTimes(2));
    expect(mocks.initialize.mock.calls[1][0].nonce).toBe("hashed-2");
    // Re-arming reuses the button already on the page rather than drawing a second one.
    expect(mocks.renderButton).toHaveBeenCalledTimes(1);
  });

  it("blocks clicks on Google's button while the form is busy", async () => {
    const { container, rerender } = render(
      <GoogleSignInButton onCredential={vi.fn()} fallback={fallback} disabled />,
    );
    await waitFor(() => expect(mocks.renderButton).toHaveBeenCalled());
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).toContain("pointer-events-none");
    expect(wrapper.getAttribute("aria-disabled")).toBe("true");

    rerender(<GoogleSignInButton onCredential={vi.fn()} fallback={fallback} />);
    expect(wrapper.className).not.toContain("pointer-events-none");
  });

  it("does nothing if it unmounts before Google's script arrives", async () => {
    let finishLoading!: (value: unknown) => void;
    mocks.load.mockReturnValue(new Promise((resolve) => (finishLoading = resolve)));
    const { unmount } = render(<GoogleSignInButton onCredential={vi.fn()} fallback={fallback} />);

    unmount();
    finishLoading({ initialize: mocks.initialize, renderButton: mocks.renderButton });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(mocks.initialize).not.toHaveBeenCalled();
    expect(mocks.renderButton).not.toHaveBeenCalled();
  });

  it("falls back to the redirect button when the script fails", async () => {
    mocks.load.mockRejectedValue(new Error("blocked"));
    render(<GoogleSignInButton onCredential={vi.fn()} fallback={fallback} />);

    expect(await screen.findByText("Fallback Google")).toBeTruthy();
  });

  it("falls back immediately without a client ID", () => {
    mocks.clientId = "";
    render(<GoogleSignInButton onCredential={vi.fn()} fallback={fallback} />);

    expect(screen.getByText("Fallback Google")).toBeTruthy();
    expect(mocks.load).not.toHaveBeenCalled();
  });
});
