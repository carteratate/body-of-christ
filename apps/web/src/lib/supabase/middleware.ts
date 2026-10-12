import { isAuthApiError, isAuthError, isAuthSessionMissingError } from "@supabase/supabase-js";
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
 * Signed out only on a definite answer: no session, a token that fails
 * verification, or Supabase Auth rejecting the session (a 4xx other than 429,
 * e.g. a revoked or already-used refresh token). Anything else — a network
 * failure, a 5xx or 429 from the JWKS or token endpoint, an unparseable
 * response — says nothing about the session, so it is unknown. When such an
 * error comes from a refresh, auth-js has already cleared the cookies, so the
 * next request sees no session and is signed out cleanly.
 */
export function authStateFromClaims({ data, error }: ClaimsResult): AuthState {
  const sub = data?.claims?.sub;
  if (typeof sub === "string" && sub) return "signed-in";
  if (!error) return "signed-out";
  if (isAuthSessionMissingError(error)) return "signed-out";
  if (isAuthError(error) && error.name === "AuthInvalidJwtError") return "signed-out";
  if (isAuthApiError(error) && error.status >= 400 && error.status < 500 && error.status !== 429) return "signed-out";
  return "unknown";
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
