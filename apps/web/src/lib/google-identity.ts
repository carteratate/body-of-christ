// Google Identity Services (GIS): Google's own "Sign in with Google" button.
// Signing in through it keeps the consent screen on theo-corpus.com instead of
// the Supabase project domain the redirect flow shows.

export const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

export const GIS_ORIGIN = "https://accounts.google.com";
export const GIS_SCRIPT_SRC = `${GIS_ORIGIN}/gsi/client`;

export interface GoogleCredentialResponse {
  credential: string;
}

export interface GoogleButtonOptions {
  theme: "outline" | "filled_blue" | "filled_black";
  size: "large" | "medium" | "small";
  text: "signin_with" | "signup_with" | "continue_with" | "signin";
  shape: "rectangular" | "pill";
  logo_alignment: "left" | "center";
  width: number;
  locale: string;
}

export interface GoogleAccountsId {
  initialize(config: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
    nonce: string;
    ux_mode: "popup";
    itp_support: boolean;
    use_fedcm_for_button: boolean;
  }): void;
  renderButton(parent: HTMLElement, options: GoogleButtonOptions): void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } };
  }
}

let loading: Promise<GoogleAccountsId> | null = null;

/** Loads the GIS script once per page; rejects if it fails or takes longer than timeoutMs. */
export function loadGoogleIdentity(timeoutMs = 5000): Promise<GoogleAccountsId> {
  if (window.google?.accounts?.id) return Promise.resolve(window.google.accounts.id);
  if (loading) return loading;

  loading = new Promise<GoogleAccountsId>((resolve, reject) => {
    const script = document.createElement("script");
    const timer = window.setTimeout(() => fail(new Error("Google sign-in timed out")), timeoutMs);

    function fail(error: Error) {
      window.clearTimeout(timer);
      script.remove();
      loading = null;
      reject(error);
    }

    script.src = GIS_SCRIPT_SRC;
    script.async = true;
    script.onload = () => {
      const id = window.google?.accounts?.id;
      if (!id) return fail(new Error("Google sign-in did not initialize"));
      window.clearTimeout(timer);
      resolve(id);
    };
    script.onerror = () => fail(new Error("Google sign-in failed to load"));
    document.head.appendChild(script);
  });
  return loading;
}

/**
 * A fresh nonce pair. Google embeds `hashed` in the ID token; Supabase hashes
 * `raw` itself and compares, so a stolen token can't be replayed.
 */
export async function createNonce(): Promise<{ raw: string; hashed: string }> {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  const raw = btoa(String.fromCharCode(...bytes)).replace(/[+/=]/g, "");
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(raw));
  const hashed = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  return { raw, hashed };
}
