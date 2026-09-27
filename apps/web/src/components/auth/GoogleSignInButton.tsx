"use client";

import { useEffect, useRef, useState } from "react";
import { preconnect, preload } from "react-dom";
import {
  createNonce,
  GIS_ORIGIN,
  GIS_SCRIPT_SRC,
  GOOGLE_CLIENT_ID,
  loadGoogleIdentity,
} from "@/lib/google-identity";

type Status = "loading" | "ready" | "fallback";

/**
 * Google's own sign-in button. It hands back an ID token plus the raw nonce
 * that Supabase needs to verify it. When the script is blocked or no client ID
 * is configured, it renders `fallback` (the redirect flow) instead.
 */
export function GoogleSignInButton({
  onCredential,
  fallback,
  disabled = false,
}: {
  onCredential: (token: string, nonce: string) => void;
  fallback: React.ReactNode;
  disabled?: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const handler = useRef(onCredential);
  const [status, setStatus] = useState<Status>(GOOGLE_CLIENT_ID ? "loading" : "fallback");

  // React hoists these into the server-rendered <head>, so the browser fetches Google's
  // script alongside the page's own JavaScript instead of after hydration.
  if (GOOGLE_CLIENT_ID) {
    preconnect(GIS_ORIGIN);
    preload(GIS_SCRIPT_SRC, { as: "script" });
  }

  useEffect(() => {
    handler.current = onCredential;
  }, [onCredential]);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    let cancelled = false;

    // Each sign-in attempt needs its own nonce, so a credential re-runs initialize with a
    // fresh one. Google uses the latest initialize for the button already on the page.
    async function setUp(render: boolean) {
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
            void setUp(false);
          },
        });
        if (!render) return;
        google.renderButton(parent, {
          theme: document.documentElement.dataset.theme === "light" ? "outline" : "filled_black",
          size: "large",
          text: "continue_with",
          shape: "rectangular",
          logo_alignment: "center",
          width: Math.min(400, Math.max(200, parent.offsetWidth)),
          // Otherwise Google follows the browser or Google account language, so the
          // button can read "Continuar com o Google" in an English-only interface.
          locale: "en",
        });
        // Google draws the button in an iframe that loads on its own; the placeholder stays
        // behind it until then so the spot never sits empty.
        const frame = parent.querySelector("iframe");
        if (frame) {
          const settle = () => !cancelled && setStatus("ready");
          frame.addEventListener("load", settle, { once: true });
          window.setTimeout(settle, 3000); // stop the placeholder pulsing even if load never fires
        } else {
          setStatus("ready");
        }
      } catch {
        if (!cancelled) setStatus("fallback");
      }
    }

    void setUp(true);
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "fallback") return <>{fallback}</>;

  // Google draws the button inside `container`; the placeholder holds its size and place until
  // then. Google's button can't be disabled itself, so the wrapper blocks clicks instead.
  return (
    <div
      className={`relative h-10 w-full ${disabled ? "pointer-events-none opacity-50" : ""}`}
      aria-busy={status === "loading"}
      aria-disabled={disabled}
    >
      {status === "loading" && (
        <div aria-hidden="true" className="absolute inset-0 animate-pulse rounded-md bg-brand-bg" />
      )}
      {/* color-scheme matches Google's light iframe document: with the site's dark scheme the
          browser would paint the iframe white until Google's own styles arrive. */}
      <div ref={container} className="relative flex h-10 w-full justify-center" style={{ colorScheme: "light" }} />
    </div>
  );
}
