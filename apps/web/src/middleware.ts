import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { authStateFromClaims, redirectWithSession, type AuthState } from "@/lib/supabase/middleware";

export default async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
          Object.entries(headers ?? {}).forEach(([key, value]) =>
            supabaseResponse.headers.set(key, value),
          );
        },
      },
    },
  );

  // Refresh the session, then verify the access token locally against the
  // project's cached JWKS: no Auth server call unless the token needs refreshing.
  // Do not add any logic between createServerClient and getClaims, and never
  // return before it: a refresh writes the rotated cookies during this call.
  let auth: AuthState;
  try {
    auth = authStateFromClaims(await supabase.auth.getClaims());
  } catch {
    auth = "unknown";
  }

  const { pathname } = request.nextUrl;
  const redirect = (path: string) => redirectWithSession(new URL(path, request.url), supabaseResponse);

  // Returning users go straight to the app.
  if (pathname === "/") {
    return auth === "signed-in" ? redirect("/search") : supabaseResponse;
  }

  // ── Guest search page rules ──────────────────────────────────────────────
  if (pathname.startsWith("/search/guest")) {
    const isDevelopmentPreview = process.env.NODE_ENV === "development" && request.nextUrl.searchParams.get("preview") === "1";
    if (isDevelopmentPreview) return supabaseResponse;
    if (auth === "signed-in") {
      // Logged-in users get the full experience
      return redirect("/search");
    }
    return supabaseResponse;
  }

  if (pathname.startsWith("/reader/guest/")) {
    const isDevelopmentPreview = process.env.NODE_ENV === "development" && request.nextUrl.searchParams.get("preview") === "1";
    if (isDevelopmentPreview) return supabaseResponse;
    if (auth === "signed-in") return redirect(pathname.replace("/reader/guest/", "/reader/") + request.nextUrl.search);
    return supabaseResponse;
  }

  if (pathname === "/guest/about" || pathname === "/guest/feedback") {
    if (auth === "signed-in") return redirect(pathname.replace("/guest", ""));
    return supabaseResponse;
  }

  if (auth === "signed-out" && (pathname === "/about" || pathname === "/feedback")) {
    return redirect(`/guest${pathname}`);
  }

  // ── Authenticated-only routes ────────────────────────────────────────────
  if (
    auth === "signed-out" &&
    (pathname.startsWith("/chat") ||
      pathname.startsWith("/search") ||
      pathname.startsWith("/history") ||
      pathname.startsWith("/bookmarks") ||
      pathname.startsWith("/reader"))
  ) {
    return redirect("/login");
  }

  if (auth === "signed-in" && (pathname === "/login" || pathname === "/signup")) {
    return redirect("/search");
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/",
    "/chat/:path*",
    "/search/:path*",
    "/history/:path*",
    "/feedback/:path*",
    "/about/:path*",
    "/guest/:path*",
    "/bookmarks/:path*",
    "/reader/:path*",
    "/login",
    "/signup",
  ],
};
