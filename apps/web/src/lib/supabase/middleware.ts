import { isAuthError, isAuthRetryableFetchError } from "@supabase/supabase-js";
import { NextResponse } from "next/server";

/**
 * What the middleware knows about the visitor. "unknown" means the session could
 * not be checked (Supabase Auth or the JWKS endpoint unreachable). It is not the
 * same as signed out: pages render no data on the server and the API checks
 * every request itself, so an unknown visitor is let through rather than sent to
 * /login. AppShell still sends a visitor with no session to /login client-side.
 */
export type AuthState = "signed-in" | "signed-out" | "unknown";

interface ClaimsResult {
  data: { claims: { sub?: unknown } } | null;
  error: unknown;
}

/**
 * Maps a `getClaims()` result to an auth state.
 *
 * Mirrors auth-js: a failed refresh clears the session unless the error is
 * retryable (network failure, 502–504), so every other auth error really is
 * signed out. AuthUnknownError (an unparseable response, e.g. from the JWKS
 * endpoint) leaves the session in place, so it is unknown too.
 */
export function authStateFromClaims({ data, error }: ClaimsResult): AuthState {
  const sub = data?.claims?.sub;
  if (typeof sub === "string" && sub) return "signed-in";
  if (!error) return "signed-out";
  if (!isAuthError(error)) return "unknown";
  if (isAuthRetryableFetchError(error) || error.name === "AuthUnknownError") return "unknown";
  return "signed-out";
}

/**
 * A redirect that carries everything the session refresh wrote onto `from`:
 * rotated auth cookies and the no-store headers Supabase sends with them.
 * Without the cookies the browser keeps an already-used refresh token, and
 * its next request can sign the person out.
 */
export function redirectWithSession(url: URL, from: NextResponse): NextResponse {
  const redirect = NextResponse.redirect(url);
  from.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
  for (const name of ["Cache-Control", "Expires", "Pragma"]) {
    const value = from.headers.get(name);
    if (value !== null) redirect.headers.set(name, value);
  }
  return redirect;
}
