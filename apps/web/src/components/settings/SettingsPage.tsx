"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Settings as SettingsIcon, Church, LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useAppContext } from "@/components/layout/AppShell";
import { updatePreferences } from "@/lib/api";
import { SettingsPageSkeleton } from "@/components/common/PageSkeletons";

function SettingsError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="p-6 max-w-lg">
      <div className="flex items-center gap-2 mb-4">
        <SettingsIcon size={20} className="text-brand-accent" />
        <h1 className="text-xl font-semibold text-brand-primary font-brand">Settings</h1>
      </div>
      <p className="text-brand-muted text-sm mb-3">We couldn&apos;t load your settings. Please try again.</p>
      <button
        onClick={onRetry}
        className="text-brand-accent text-sm hover:underline"
      >
        Retry
      </button>
    </div>
  );
}

export function SettingsPage() {
  const router = useRouter();
  const { ready, token, preferences, setPreferences, preferencesError } = useAppContext();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    setSignOutError(null);
    const supabase = createClient();
    const { error } = await supabase.auth.signOut();
    if (error) {
      setSignOutError("Couldn't sign out. Please try again.");
      setSigningOut(false);
      return;
    }
    router.replace("/login");
  }

  const isLoading = !ready || (ready && !!token && preferences === null && !preferencesError);

  if (isLoading) return <SettingsPageSkeleton />;
  if (preferencesError) return <SettingsError onRetry={() => window.location.reload()} />;
  if (!preferences) return <SettingsError onRetry={() => window.location.reload()} />;

  const theme = preferences.theme ?? "dark";

  async function handleThemeToggle(next: "dark" | "light") {
    if (!token || !preferences) return;

    // Apply immediately — no round-trip delay
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theocorpus-theme", next); } catch {}
    document.cookie = `theocorpus-theme=${next}; path=/; max-age=31536000; SameSite=Lax`;
    setPreferences({ ...preferences, theme: next });

    setSaving(true);
    setSaveError(null);
    try {
      const saved = await updatePreferences(token, { theme: next });
      setPreferences(saved);
    } catch {
      setSaveError("Couldn't save preference. It will reset on next load.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-6 max-w-lg">
      <div className="flex items-center gap-2 mb-6">
        <SettingsIcon size={20} className="text-brand-accent" />
        <h1 className="text-xl font-semibold text-brand-primary font-brand">Settings</h1>
      </div>

      {/* Appearance */}
      <section className="rounded-lg bg-brand-surface p-4">
        <h2 className="text-xs font-semibold text-brand-muted uppercase tracking-widest mb-3">
          Appearance
        </h2>

        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-brand-primary">Theme</p>
            <p className="text-xs text-brand-muted mt-0.5">
              {theme === "dark" ? "Slate Night" : "Ivory"}
            </p>
          </div>

          {/* Toggle pill */}
          <button
            onClick={() => handleThemeToggle(theme === "dark" ? "light" : "dark")}
            disabled={saving}
            role="switch"
            aria-checked={theme === "light"}
            aria-label="Toggle light/dark mode"
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent disabled:opacity-50 ${
              theme === "light" ? "bg-brand-accent" : "bg-brand-muted/50"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                theme === "light" ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>

      </section>

      {saveError && (
        <p className="text-brand-danger text-xs mt-3">{saveError}</p>
      )}
      {saving && (
        <p className="text-brand-muted text-xs mt-3">Saving…</p>
      )}

      {/* About */}
      <section className="rounded-lg bg-brand-surface p-4 mt-4">
        <h2 className="text-xs font-semibold text-brand-muted uppercase tracking-widest mb-3">
          Info
        </h2>
        <Link
          href="/about"
          className="flex items-center gap-2 text-sm text-brand-primary hover:text-brand-accent transition-colors"
        >
          <Church size={16} />
          About
        </Link>
      </section>

      {/* Sign out */}
      <section className="rounded-lg bg-brand-surface p-4 mt-4">
        <h2 className="text-xs font-semibold text-brand-muted uppercase tracking-widest mb-3">
          Account
        </h2>
          <button
            onClick={handleSignOut}
            disabled={signingOut}
            className="flex items-center gap-2 text-sm text-brand-primary hover:text-red-400 transition-colors disabled:opacity-50"
        >
          <LogOut size={16} />
          {signingOut ? "Signing out…" : "Sign out"}
          </button>
          {signOutError && <p className="text-brand-danger text-xs mt-2">{signOutError}</p>}
      </section>
    </div>
  );
}
