"use client";

import posthog from "posthog-js";
import { PostHogProvider as PHProvider } from "posthog-js/react";
import { useEffect } from "react";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    const host = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";
    if (key) {
      posthog.init(key, {
        api_host: host,
        person_profiles: "identified_only",
        capture_pageview: true,
      });
    }
  }, []);

  if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) {
    // PostHog not configured — just render children without the provider
    return <>{children}</>;
  }

  return <PHProvider client={posthog}>{children}</PHProvider>;
}
