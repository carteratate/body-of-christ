// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveFeedbackContext } from "@/lib/feedbackContext";
import { FeedbackPage } from "./FeedbackPage";

const mocks = vi.hoisted(() => ({ submit: vi.fn(), track: vi.fn(), token: "token" as string | null }));
vi.mock("@/components/layout/AppShell", () => ({ useAppContext: () => ({ token: mocks.token }) }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  submitProductFeedback: mocks.submit,
}));
vi.mock("@/lib/analytics", () => ({ trackFeedbackSubmitted: mocks.track }));

beforeEach(() => {
  sessionStorage.clear();
  mocks.submit.mockReset();
  mocks.track.mockReset();
  mocks.token = "token";
});

afterEach(cleanup);

describe("FeedbackPage", () => {
  it("provides a visible focus treatment for keyboard-focused category choices", async () => {
    render(<FeedbackPage />);
    const radio = screen.getByRole("radio", { name: /Something isn't working/ });
    radio.focus();
    expect(radio.closest("label")?.className).toContain("focus-within:ring-2");
  });

  it("submits bounded context without placing report text in the URL", async () => {
    saveFeedbackContext({
      category: "content",
      origin: "search_result",
      route: "/search",
      search_id: "00000000-0000-0000-0000-000000000001",
      chunk_id: "00000000-0000-0000-0000-000000000002",
      document_id: "00000000-0000-0000-0000-000000000003",
    });
    mocks.submit.mockResolvedValue({ feedback_id: "12345678-0000-0000-0000-000000000000" });
    render(<FeedbackPage />);

    expect((screen.getByRole("radio", { name: /Content issue/ }) as HTMLInputElement).checked).toBe(true);
    await userEvent.type(screen.getByRole("textbox", { name: /Details/ }), "The citation opens the wrong passage.");
    await userEvent.click(screen.getByRole("button", { name: "Send feedback" }));

    await screen.findByText("Thank you for helping improve TheoCorpus");
    expect(mocks.submit).toHaveBeenCalledWith("token", expect.objectContaining({
      category: "content",
      route: "/search",
      search_id: "00000000-0000-0000-0000-000000000001",
      chunk_id: "00000000-0000-0000-0000-000000000002",
      document_id: "00000000-0000-0000-0000-000000000003",
    }));
    expect(window.location.search).toBe("");
  });

  it("keeps the user's draft when submission fails", async () => {
    mocks.submit.mockRejectedValue(new Error("Service temporarily unavailable"));
    render(<FeedbackPage />);
    const details = screen.getByRole("textbox", { name: /Details/ });
    await userEvent.type(details, "Please add a better mobile reading layout.");
    await userEvent.click(screen.getByRole("button", { name: "Send feedback" }));

    await screen.findByRole("alert");
    expect((details as HTMLTextAreaElement).value).toBe("Please add a better mobile reading layout.");
    await waitFor(() => expect((screen.getByRole("button", { name: "Send feedback" }) as HTMLButtonElement).disabled).toBe(false));
  });

  it("submits anonymously without account context or contact permission", async () => {
    mocks.token = null;
    saveFeedbackContext({
      category: "bug",
      origin: "reader",
      route: "/reader",
      search_id: "00000000-0000-0000-0000-000000000001",
      chunk_id: "00000000-0000-0000-0000-000000000002",
    });
    mocks.submit.mockResolvedValue({ feedback_id: "12345678-0000-0000-0000-000000000000" });
    render(<FeedbackPage />);

    expect(screen.getByText(/This report is anonymous/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    await userEvent.type(screen.getByRole("textbox", { name: /Details/ }), "The guest reader stopped opening chapters.");
    await userEvent.click(screen.getByRole("button", { name: "Send feedback" }));

    await waitFor(() => expect(mocks.submit).toHaveBeenCalledWith(null, expect.objectContaining({
      contact_allowed: false,
      route: "/reader",
      search_id: undefined,
      chunk_id: undefined,
      document_id: undefined,
    })));
  });
});
