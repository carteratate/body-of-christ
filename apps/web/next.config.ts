import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

// script-src and default-src intentionally omitted: Next.js requires inline scripts
// for hydration (__NEXT_DATA__). Adding 'unsafe-inline' would defeat XSS protection;
// proper nonce-based CSP requires per-request middleware and is deferred.
// The directives below still provide meaningful protection.
const cspDirectives = [
  // PostHog's US ingestion and asset hosts. posthog-js sends app.posthog.com to
  // us.i.posthog.com itself, so the legacy host alone would block every event.
  `connect-src 'self' https://us.i.posthog.com https://us-assets.i.posthog.com${apiUrl ? ` ${apiUrl}` : ""}${supabaseUrl ? ` ${supabaseUrl}` : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // apps/web/AGENTS.md is a committed file (see the root CLAUDE.md); without this,
  // `next dev` rewrites its managed block whenever an agent runs the dev server.
  agentRules: false,
  ...(process.env.NODE_ENV === "development"
    ? { allowedDevOrigins: ["127.0.0.1"] }
    : {}),
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
