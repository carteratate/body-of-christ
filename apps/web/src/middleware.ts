import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

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
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // Refresh session — do not add any logic between createServerClient and getUser
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  // ── Guest search page rules ──────────────────────────────────────────────
  if (pathname.startsWith("/search/guest")) {
    const isDevelopmentPreview = process.env.NODE_ENV === "development" && request.nextUrl.searchParams.get("preview") === "1";
    if (isDevelopmentPreview) return supabaseResponse;
    if (user) {
      // Logged-in users get the full experience
      return NextResponse.redirect(new URL("/search", request.url));
    }
    return supabaseResponse;
  }

  if (pathname.startsWith("/reader/guest/")) {
    const isDevelopmentPreview = process.env.NODE_ENV === "development" && request.nextUrl.searchParams.get("preview") === "1";
    if (isDevelopmentPreview) return supabaseResponse;
    if (user) return NextResponse.redirect(new URL(pathname.replace("/reader/guest/", "/reader/") + request.nextUrl.search, request.url));
    return supabaseResponse;
  }

  // ── Authenticated-only routes ────────────────────────────────────────────
  if (
    !user &&
    (pathname.startsWith("/chat") ||
      pathname.startsWith("/search") ||
      pathname.startsWith("/history") ||
      pathname.startsWith("/feedback") ||
      pathname.startsWith("/bookmarks") ||
      pathname.startsWith("/reader"))
  ) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (user && (pathname === "/login" || pathname === "/signup")) {
    return NextResponse.redirect(new URL("/search", request.url));
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/chat/:path*",
    "/search/:path*",
    "/history/:path*",
    "/feedback/:path*",
    "/bookmarks/:path*",
    "/reader/:path*",
    "/login",
    "/signup",
  ],
};
