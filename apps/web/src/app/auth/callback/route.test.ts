import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

type CookieWriter = { setAll: (cookies: { name: string; value: string; options: object }[]) => void };

const mocks = vi.hoisted(() => ({
  exchangeCodeForSession: vi.fn(),
  cookies: null as CookieWriter | null,
}));
const exchangeCodeForSession = mocks.exchangeCodeForSession;

vi.mock("@supabase/ssr", () => ({
  createServerClient: (_url: string, _key: string, options: { cookies: CookieWriter }) => {
    mocks.cookies = options.cookies;
    return { auth: { exchangeCodeForSession } };
  },
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

  it("writes the session cookies onto the redirect", async () => {
    exchangeCodeForSession.mockImplementation(async () => {
      mocks.cookies?.setAll([{ name: "sb-test-auth-token", value: "session", options: { path: "/" } }]);
      return { error: null };
    });
    const response = await callback("code=abc&next=/search");
    expect(response.cookies.get("sb-test-auth-token")?.value).toBe("session");
  });

  it.each(["//evil.example", "@evil.example", "https://evil.example"])(
    "ignores a next of %s that would leave the site",
    async (next) => {
      const response = await callback(`code=abc&next=${encodeURIComponent(next)}`);
      expect(response.headers.get("location")).toBe("http://localhost:3000/search");
    },
  );

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
