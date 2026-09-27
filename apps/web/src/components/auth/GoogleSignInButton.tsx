"use client";

import { useEffect, useRef, useState } from "react";
import { createNonce, GOOGLE_CLIENT_ID, loadGoogleIdentity } from "@/lib/google-identity";

type Status = "loading" | "ready" | "fallback";

/**
 * Google's own sign-in button. It hands back an ID token plus the raw nonce
 * that Supabase needs to verify it. When the script is blocked or no client ID
 * is configured, it renders `fallback` (the redirect flow) instead.
 */
export function GoogleSignInButton({
  onCredential,
  fallback,
}: {
  onCredential: (token: string, nonce: string) => void;
  fallback: React.ReactNode;
}) {
  const container = useRef<HTMLDivElement>(null);
  const handler = useRef(onCredential);
  const [status, setStatus] = useState<Status>(GOOGLE_CLIENT_ID ? "loading" : "fallback");

  useEffect(() => {
    handler.current = onCredential;
  }, [onCredential]);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    let cancelled = false;

    // Each sign-in attempt needs its own nonce, so this runs again after a credential arrives.
    async function setUp() {
      try {
        const [google, nonce] = await Promise.all([loadGoogleIdentity(), createNonce()]);
        const parent = container.current;
        if (cancelled || !parent) return;

        google.initialize({
          client_id: GOOGLE_CLIENT_ID,
          nonce: nonce.hashed,
          ux_mode: "popup",
          itp_support: true,
          use_fedcm_for_button: true,
          callback: ({ credential }) => {
            handler.current(credential, nonce.raw);
            void setUp();
          },
        });
        google.renderButton(parent, {
          theme: document.documentElement.dataset.theme === "light" ? "outline" : "filled_black",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          logo_alignment: "center",
          width: Math.min(400, Math.max(200, parent.offsetWidth)),
        });
        setStatus("ready");
      } catch {
        if (!cancelled) setStatus("fallback");
      }
    }

    void setUp();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "fallback") return <>{fallback}</>;

  // Google draws the button inside this div; the fixed height stops the form jumping while it loads.
  return <div ref={container} className="flex h-10 w-full justify-center" aria-busy={status === "loading"} />;
}
