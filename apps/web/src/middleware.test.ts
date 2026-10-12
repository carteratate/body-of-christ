import { AuthApiError, AuthInvalidJwtError, AuthRetryableFetchError, AuthSessionMissingError, AuthUnknownError } from "@supabase/supabase-js";
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

type CookieToSet = { name: string; value: string; options?: Record<string, unknown> };
type CookieMethods = {
  getAll: () => { name: string; value: string }[];
  setAll: (cookies: CookieToSet[], headers: Record<string, string>) => void;
};

const supabaseState = vi.hoisted(() => ({
  getClaims: vi.fn(),
  getUser: vi.fn(),
  cookieMethods: null as unknown,
}));

vi.mock("@supabase/ssr", () => ({
  createServerClient: (_url: string, _key: string, options: { cookies: unknown }) => {
    supabaseState.cookieMethods = options.cookies;
    return { auth: { getClaims: supabaseState.getClaims, getUser: supabaseState.getUser } };
  },
}));

const { default: middleware, config } = await import("./middleware");

const REFRESHED = [
  { name: "sb-test-auth-token", value: "rotated", options: { path: "/", sameSite: "lax", maxAge: 400 } },
];
const NO_STORE = { "Cache-Control": "private, no-cache, no-store, must-revalidate, max-age=0", Expires: "0", Pragma: "no-cache" };

function signedIn() {
  return { data: { claims: { sub: "user-1" }, header: {}, signature: new Uint8Array() }, error: null };
}
function signedOut() {
  return { data: null, error: null };
}
function failed(error: unknown) {
  return { data: null, error };
}

/** getClaims that rotates the session cookies before resolving, as a refresh does. */
function refreshingThen(result: unknown) {
  return async () => {
    (supabaseState.cookieMethods as CookieMethods).setAll(REFRESHED, NO_STORE);
    return result;
  };
}

function run(path: string) {
  return middleware(new NextRequest(new URL(path, "http://localhost:3000")));
}

function location(response: Response) {
  const value = response.headers.get("location");
  return value ? new URL(value).pathname + new URL(value).search : null;
}

beforeEach(() => {
  supabaseState.getClaims.mockReset();
  supabaseState.getUser.mockReset();
});

describe("middleware session check", () => {
  it("verifies with getClaims and never asks the Auth server for the user", async () => {
    supabaseState.getClaims.mockResolvedValue(signedIn());
    await run("/search");
    expect(supabaseState.getClaims).toHaveBeenCalledTimes(1);
    expect(supabaseState.getUser).not.toHaveBeenCalled();
  });

  it("lets a signed-in user through protected routes", async () => {
    supabaseState.getClaims.mockResolvedValue(signedIn());
    for (const path of ["/search", "/history", "/bookmarks", "/reader/doc-a?chapter=c1", "/about", "/feedback"]) {
      expect(location(await run(path)), path).toBeNull();
    }
  });

  it("sends a visitor with no session to /login from protected routes", async () => {
    supabaseState.getClaims.mockResolvedValue(signedOut());
    for (const path of ["/search", "/history", "/bookmarks", "/reader/doc-a", "/chat"]) {
      expect(location(await run(path)), path).toBe("/login");
    }
  });

  it("sends a visitor with no session to the guest About and Feedback pages", async () => {
    supabaseState.getClaims.mockResolvedValue(signedOut());
    expect(location(await run("/about"))).toBe("/guest/about");
    expect(location(await run("/feedback"))).toBe("/guest/feedback");
    expect(location(await run("/guest/about"))).toBeNull();
  });

  it("sends a signed-in user away from login, signup and guest pages", async () => {
    supabaseState.getClaims.mockResolvedValue(signedIn());
    expect(location(await run("/login"))).toBe("/search");
    expect(location(await run("/signup"))).toBe("/search");
    expect(location(await run("/search/guest"))).toBe("/search");
    expect(location(await run("/guest/feedback"))).toBe("/feedback");
    expect(location(await run("/reader/guest/doc-a?anchor=p3&from=search"))).toBe("/reader/doc-a?anchor=p3&from=search");
  });

  it("treats a session that could not be checked as unknown, not signed out", async () => {
    for (const error of [
      new AuthRetryableFetchError("fetch failed", 0),
      new AuthRetryableFetchError("Bad Gateway", 502),
      new AuthUnknownError("Unexpected token <", new SyntaxError("bad json")),
      // A JWKS or token endpoint failing says nothing about the session.
      new AuthApiError("Internal Server Error", 500, "unexpected_failure"),
      new AuthApiError("Too Many Requests", 429, "over_request_rate_limit"),
    ]) {
      supabaseState.getClaims.mockResolvedValue(failed(error));
      expect(location(await run("/search")), error.message).toBeNull();
      expect(location(await run("/reader/doc-a")), error.message).toBeNull();
      expect(location(await run("/about")), error.message).toBeNull();
      // Unknown is not signed in either: no redirect away from the auth pages.
      expect(location(await run("/login")), error.message).toBeNull();
      expect(location(await run("/")), error.message).toBeNull();
    }
  });

  it("treats a thrown verification failure as unknown", async () => {
    supabaseState.getClaims.mockRejectedValue(new TypeError("crypto.subtle unavailable"));
    expect(location(await run("/search"))).toBeNull();
  });

  it("treats a rejected session as signed out", async () => {
    for (const error of [
      new AuthApiError("Invalid Refresh Token: Already Used", 400, "refresh_token_already_used"),
      new AuthSessionMissingError(),
      new AuthApiError("Session not found", 403, "session_not_found"),
      new AuthInvalidJwtError("Invalid JWT signature"),
    ]) {
      supabaseState.getClaims.mockResolvedValue(failed(error));
      expect(location(await run("/search")), error.message).toBe("/login");
    }
  });

  it("redirects a signed-in visitor on / to /search and leaves everyone else on the landing page", async () => {
    supabaseState.getClaims.mockResolvedValue(signedIn());
    expect(location(await run("/"))).toBe("/search");
    supabaseState.getClaims.mockResolvedValue(signedOut());
    expect(location(await run("/"))).toBeNull();
    expect(config.matcher).toContain("/");
  });
});

describe("middleware refreshed cookies", () => {
  it("carries rotated cookies and no-store headers onto a pass-through response", async () => {
    supabaseState.getClaims.mockImplementation(refreshingThen(signedIn()));
    const response = await run("/search");
    expect(location(response)).toBeNull();
    expect(response.headers.get("set-cookie")).toContain("sb-test-auth-token=rotated");
    expect(response.headers.get("cache-control")).toBe(NO_STORE["Cache-Control"]);
  });

  it.each([
    ["/", "/search", signedIn()],
    ["/login", "/search", signedIn()],
    ["/search/guest", "/search", signedIn()],
    ["/reader/guest/doc-a", "/reader/doc-a", signedIn()],
    ["/guest/about", "/about", signedIn()],
    ["/about", "/guest/about", signedOut()],
    ["/history", "/login", signedOut()],
  ])("carries rotated cookies onto the redirect from %s", async (path, destination, result) => {
    supabaseState.getClaims.mockImplementation(refreshingThen(result));
    const response = await run(path);
    expect(location(response)).toBe(destination);
    const setCookie = response.headers.get("set-cookie") ?? "";
    expect(setCookie).toContain("sb-test-auth-token=rotated");
    expect(setCookie).toContain("Max-Age=400");
    expect(response.headers.get("cache-control")).toBe(NO_STORE["Cache-Control"]);
    expect(response.headers.get("pragma")).toBe("no-cache");
  });
});
