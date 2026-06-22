import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

// script-src and default-src intentionally omitted: Next.js requires inline scripts
// for hydration (__NEXT_DATA__). Adding 'unsafe-inline' would defeat XSS protection;
// proper nonce-based CSP requires per-request middleware and is deferred.
// The directives below still provide meaningful protection.
const cspDirectives = [
  `connect-src 'self' https://app.posthog.com https://eu.posthog.com${apiUrl ? ` ${apiUrl}` : ""}${supabaseUrl ? ` ${supabaseUrl}` : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: cspDirectives,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
