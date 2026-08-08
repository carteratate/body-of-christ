"use client";

import posthog from "posthog-js";
import { PostHogProvider as PHProvider } from "posthog-js/react";
import { useEffect } from "react";
import { usePathname } from "next/navigation";

export function sanitizeAnalyticsProperties(properties: Record<string, unknown>): Record<string, unknown> {
  const sanitized = { ...properties };
  const currentUrl = sanitized.$current_url;
  if (typeof currentUrl === "string") {
    try {
      sanitized.$current_url = new URL(currentUrl, window.location.origin).pathname;
    } catch {
      delete sanitized.$current_url;
    }
  }
  // Referrers can contain user-entered query strings on search/explore routes.
  delete sanitized.$referrer;
  return sanitized;
}

function PrivacySafePageView() {
  const pathname = usePathname();
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (process.env.NEXT_PUBLIC_POSTHOG_KEY) {
        posthog.capture("$pageview", { $current_url: pathname });
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [pathname]);
  return null;
}

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    const host = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";
    if (key) {
      posthog.init(key, {
        api_host: host,
        person_profiles: "identified_only",
        capture_pageview: false,
        autocapture: false,
        disable_session_recording: true,
        sanitize_properties: sanitizeAnalyticsProperties,
      });
    }
  }, []);

  if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) {
    // PostHog not configured — just render children without the provider
    return <>{children}</>;
  }

  return <PHProvider client={posthog}><PrivacySafePageView />{children}</PHProvider>;
}
