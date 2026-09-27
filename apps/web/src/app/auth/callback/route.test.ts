import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const exchangeCodeForSession = vi.hoisted(() => vi.fn());

vi.mock("@supabase/ssr", () => ({
  createServerClient: () => ({ auth: { exchangeCodeForSession } }),
}));

import { GET } from "./route";

function callback(query: string) {
  return GET(new NextRequest(`http://localhost:3000/auth/callback?${query}`));
}

beforeEach(() => {
  exchangeCodeForSession.mockReset();
  exchangeCodeForSession.mockResolvedValue({ error: null });
});

describe("GET /auth/callback", () => {
  it("signs in and continues to next", async () => {
    const response = await callback("code=abc&next=/search&flow=google");
    expect(response.headers.get("location")).toBe("http://localhost:3000/search");
  });

  it("reports an unfinished Google sign-in", async () => {
    const response = await callback("next=/search&flow=google&error=access_denied");
    expect(response.headers.get("location")).toBe("http://localhost:3000/login?error=oauth");
  });

  it("keeps the expired-link message for a failed email confirmation", async () => {
    const response = await callback("next=/search&error=access_denied&error_code=otp_expired");
    expect(response.headers.get("location")).toBe("http://localhost:3000/login?error=auth");
  });

  it("reports a failed code exchange from Google as a Google failure", async () => {
    exchangeCodeForSession.mockResolvedValue({ error: new Error("bad code") });
    const response = await callback("code=abc&next=/search&flow=google");
    expect(response.headers.get("location")).toBe("http://localhost:3000/login?error=oauth");
  });
});
