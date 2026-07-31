"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

type AuthMode = "sign-in" | "sign-up" | "forgot-password";

export function LoginForm() {
  const router = useRouter();
  const [supabase] = useState(createClient);
  const [mode, setMode] = useState<AuthMode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY") {
        router.replace("/update-password");
      } else if (session) {
        router.replace("/search");
      }
    });
    return () => subscription.unsubscribe();
  }, [router, supabase]);

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode);
    setPassword("");
    setConfirmPassword("");
    setError(null);
    setMessage(null);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    if (mode === "sign-up" && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    if (mode === "sign-in") {
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (signInError) setError(signInError.message);
    } else if (mode === "sign-up") {
      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/search` },
      });
      if (signUpError) {
        setError(signUpError.message);
      } else if (!data.session) {
        setMessage("Check your email to confirm your account.");
      }
    } else {
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/update-password`,
      });
      if (resetError) {
        setError(resetError.message);
      } else {
        setMessage("Check your email for a password reset link.");
      }
    }

    setLoading(false);
  }

  const isSignUp = mode === "sign-up";
  const passwordMismatch =
    isSignUp && confirmPassword.length > 0 && password !== confirmPassword;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <h2 className="text-center text-lg font-semibold text-brand-primary">
        {mode === "sign-in"
          ? "Sign in"
          : mode === "sign-up"
            ? "Create an account"
            : "Reset your password"}
      </h2>

      <div>
        <label htmlFor="email" className="mb-1 block text-sm text-brand-muted">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          className="w-full rounded-md border border-brand-surface bg-brand-bg px-3 py-2 text-brand-primary placeholder:text-brand-muted focus:border-brand-accent focus:outline-none"
          placeholder="you@example.com"
        />
      </div>

      {mode !== "forgot-password" && (
        <div>
          <label htmlFor="password" className="mb-1 block text-sm text-brand-muted">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete={isSignUp ? "new-password" : "current-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={8}
            className="w-full rounded-md border border-brand-surface bg-brand-bg px-3 py-2 text-brand-primary placeholder:text-brand-muted focus:border-brand-accent focus:outline-none"
            placeholder={isSignUp ? "At least 8 characters" : "Your password"}
          />
        </div>
      )}

      {isSignUp && (
        <div>
          <label
            htmlFor="confirm-password"
            className="mb-1 block text-sm text-brand-muted"
          >
            Confirm password
          </label>
          <input
            id="confirm-password"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            minLength={8}
            aria-invalid={passwordMismatch}
            aria-describedby={passwordMismatch ? "password-mismatch" : undefined}
            className="w-full rounded-md border border-brand-surface bg-brand-bg px-3 py-2 text-brand-primary placeholder:text-brand-muted focus:border-brand-accent focus:outline-none"
            placeholder="Type your password again"
          />
          {passwordMismatch && (
            <p id="password-mismatch" className="mt-1 text-sm text-brand-danger">
              Passwords do not match.
            </p>
          )}
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-brand-danger">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="text-sm text-brand-primary">
          {message}
        </p>
      )}

      <button
        type="submit"
        disabled={loading || passwordMismatch}
        className="w-full rounded-md bg-brand-accent py-2 text-sm font-semibold text-brand-bg transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {loading
          ? "Please wait…"
          : mode === "sign-in"
            ? "Sign in"
            : mode === "sign-up"
              ? "Create account"
              : "Send reset link"}
      </button>

      <div className="space-y-2 text-center text-sm">
        {mode === "sign-in" && (
          <>
            <button
              type="button"
              onClick={() => changeMode("forgot-password")}
              className="block w-full text-brand-accent hover:opacity-80"
            >
              Forgot your password?
            </button>
            <p className="text-brand-muted">
              Don&apos;t have an account?{" "}
              <button
                type="button"
                onClick={() => changeMode("sign-up")}
                className="text-brand-accent hover:opacity-80"
              >
                Sign up
              </button>
            </p>
          </>
        )}
        {mode !== "sign-in" && (
          <button
            type="button"
            onClick={() => changeMode("sign-in")}
            className="text-brand-accent hover:opacity-80"
          >
            Back to sign in
          </button>
        )}
      </div>
    </form>
  );
}
