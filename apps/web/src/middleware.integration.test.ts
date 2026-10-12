// Runs the middleware against the real @supabase/ssr and auth-js, with only the
// network faked: tokens are signed with a generated ES256 key served as the JWKS.
import { NextRequest } from "next/server";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const SUPABASE_URL = "https://test.supabase.co";
const COOKIE = "sb-test-auth-token";
const KID = "test-key";

let privateKey: CryptoKey;
let publicJwk: JsonWebKey & { kid: string };
let calls: string[];
let refreshResponse: () => Response;

function base64url(input: string | Uint8Array): string {
  const bytes = typeof input === "string" ? new TextEncoder().encode(input) : input;
  return Buffer.from(bytes).toString("base64url");
}

async function signJwt(payload: Record<string, unknown>): Promise<string> {
  const header = base64url(JSON.stringify({ alg: "ES256", kid: KID, typ: "JWT" }));
  const body = base64url(JSON.stringify(payload));
  const signature = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, privateKey, new TextEncoder().encode(`${header}.${body}`));
  return `${header}.${body}.${base64url(new Uint8Array(signature))}`;
}

async function session(expiresInSeconds: number, refreshToken: string) {
  const now = Math.floor(Date.now() / 1000);
  const exp = now + expiresInSeconds;
  return {
    access_token: await signJwt({ sub: "user-1", aud: "authenticated", role: "authenticated", iat: now - 60, exp }),
    token_type: "bearer",
    expires_in: expiresInSeconds,
    expires_at: exp,
    refresh_token: refreshToken,
    user: { id: "user-1", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" },
  };
}

function sessionCookie(value: object): string {
  return `${COOKIE}=base64-${base64url(JSON.stringify(value))}`;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function run(path: string, cookie?: string) {
  vi.resetModules();
  const { default: middleware } = await import("./middleware");
  const headers = new Headers(cookie ? { cookie } : {});
  return middleware(new NextRequest(new URL(path, "http://localhost:3000"), { headers }));
}

function location(response: Response) {
  const value = response.headers.get("location");
  return value ? new URL(value).pathname : null;
}

beforeAll(async () => {
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
  privateKey = pair.privateKey;
  publicJwk = { ...(await crypto.subtle.exportKey("jwk", pair.publicKey)), kid: KID, alg: "ES256", use: "sig" };
});

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", SUPABASE_URL);
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-key");
  calls = [];
  refreshResponse = () => json({ error: "unexpected refresh" }, 500);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    calls.push(url.pathname + url.search);
    if (url.pathname === "/auth/v1/.well-known/jwks.json") return json({ keys: [publicJwk] });
    if (url.pathname === "/auth/v1/token") return refreshResponse();
    return json({ message: "unexpected request" }, 500);
  }));
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("middleware with real Supabase clients", () => {
  it("verifies a valid token locally: one JWKS fetch, no Auth user call", async () => {
    const response = await run("/search", sessionCookie(await session(3600, "refresh-1")));
    expect(location(response)).toBeNull();
    expect(calls).toEqual(["/auth/v1/.well-known/jwks.json"]);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("rejects a token signed by another key", async () => {
    const valid = await session(3600, "refresh-1");
    const [header, body] = valid.access_token.split(".");
    const forged = { ...valid, access_token: `${header}.${body}.${base64url(new Uint8Array(64))}` };
    expect(location(await run("/search", sessionCookie(forged)))).toBe("/login");
  });

  it("refreshes an expired session and writes the rotated cookies", async () => {
    const rotated = await session(3600, "refresh-2");
    refreshResponse = () => json(rotated);
    const response = await run("/search", sessionCookie(await session(-10, "refresh-1")));
    expect(location(response)).toBeNull();
    expect(calls).toContain("/auth/v1/token?grant_type=refresh_token");
    expect(calls).not.toContain("/auth/v1/user");
    const setCookie = response.headers.get("set-cookie") ?? "";
    expect(setCookie).toContain(`${COOKIE}=base64-`);
    expect(response.headers.get("cache-control")).toContain("no-store");
  });

  it("carries the rotated cookies onto a redirect", async () => {
    const rotated = await session(3600, "refresh-2");
    refreshResponse = () => json(rotated);
    const response = await run("/login", sessionCookie(await session(-10, "refresh-1")));
    expect(location(response)).toBe("/search");
    expect(response.headers.get("set-cookie") ?? "").toContain(`${COOKIE}=base64-`);
  });

  it("sends a session whose refresh token was revoked to /login and clears it", async () => {
    refreshResponse = () => json({ code: "refresh_token_already_used", message: "Invalid Refresh Token: Already Used" }, 400);
    const response = await run("/history", sessionCookie(await session(-10, "refresh-1")));
    expect(location(response)).toBe("/login");
    expect(response.headers.get("set-cookie") ?? "").toMatch(new RegExp(`${COOKIE}=;.*Max-Age=0`));
  });

  it("lets a request through when the refresh cannot reach Supabase", async () => {
    refreshResponse = () => { throw new TypeError("fetch failed"); };
    const cookie = sessionCookie(await session(-10, "refresh-1"));
    // auth-js retries a failed refresh with backoff for up to ~25s; skip the waits.
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    let settled = false;
    const pending = run("/history", cookie).finally(() => { settled = true; });
    while (!settled) await vi.advanceTimersByTimeAsync(1_000);
    vi.useRealTimers();
    const response = await pending;
    expect(calls.filter((call) => call.startsWith("/auth/v1/token")).length).toBeGreaterThan(1);
    expect(location(response)).toBeNull();
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("treats no cookie as signed out without any network call", async () => {
    expect(location(await run("/bookmarks"))).toBe("/login");
    expect(calls).toEqual([]);
  });
});
