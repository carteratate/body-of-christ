"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

export default function UpdatePasswordPage() {
  const router = useRouter();
  const [supabase] = useState(createClient);
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const didRecover = useRef(false);

  useEffect(() => {
    // createBrowserClient clears ?code= from the URL synchronously on init,
    // before useEffect runs — so we cannot use URL params to detect recovery.
    // Instead: any session found on this page came from a reset link (nothing
    // else navigates here), so treat any session as a valid recovery.
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if ((event === "SIGNED_IN" || event === "PASSWORD_RECOVERY") && session) {
        didRecover.current = true;
        setReady(true);
      }
    });

    // Fallback: exchange may have completed before listener registered
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session && !didRecover.current) {
        didRecover.current = true;
        setReady(true);
      }
    });

    const timeout = setTimeout(() => {
      if (!didRecover.current) router.replace("/login");
    }, 5000);

    return () => {
      subscription.unsubscribe();
      clearTimeout(timeout);
    };
  }, [supabase, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setLoading(true);
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password });

      if (updateError) {
        setError(updateError.message);
        return;
      }

      setSuccess(true);
      setTimeout(() => router.replace("/search"), 1500);
    } catch {
      setError("We couldn't update your password. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (!ready) {
    return (
      <div className="flex min-h-full items-center justify-center bg-brand-bg">
        <p className="text-brand-muted text-sm">Verifying reset link…</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-brand-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1
            className="text-3xl font-semibold text-brand-accent"
            style={{ fontFamily: "var(--font-cinzel)" }}
          >
            TheoCorpus
          </h1>
          <p className="mt-2 text-sm text-brand-muted">Set your new password</p>
        </div>

        <div className="rounded-xl border border-brand-surface bg-brand-surface p-6">
          {success ? (
            <p className="text-center text-sm text-brand-primary">
              Password updated. Redirecting…
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="password" className="block text-sm text-brand-muted mb-1">
                  New password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  required
                  minLength={8}
                  className="w-full rounded-md border border-brand-surface bg-brand-bg px-3 py-2 text-brand-primary placeholder:text-brand-muted focus:border-brand-accent focus:outline-none"
                  placeholder="At least 8 characters"
                />
              </div>
              <div>
                <label htmlFor="confirm" className="block text-sm text-brand-muted mb-1">
                  Confirm password
                </label>
                <input
                  id="confirm"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  disabled={loading}
                  required
                  className="w-full rounded-md border border-brand-surface bg-brand-bg px-3 py-2 text-brand-primary placeholder:text-brand-muted focus:border-brand-accent focus:outline-none"
                  placeholder="Repeat new password"
                />
              </div>
              {error && <p className="text-sm text-brand-danger">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-md bg-brand-accent py-2 text-sm font-semibold text-brand-bg hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {loading ? "Updating…" : "Update password"}
              </button>
              <p className="text-center text-sm text-brand-muted">
                <a href="/login" className="text-brand-accent hover:opacity-80">
                  Back to sign in
                </a>
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
