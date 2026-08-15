"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import { Bug, CheckCircle2, Lightbulb, MessageSquareText, ShieldCheck } from "lucide-react";

import { useAppContext } from "@/components/layout/AppShell";
import { trackFeedbackSubmitted } from "@/lib/analytics";
import { clearFeedbackContext, parseFeedbackContext, readFeedbackContextRaw, subscribeFeedbackContext } from "@/lib/feedbackContext";
import { submitProductFeedback, type ProductFeedbackCategory } from "@/lib/api";

const CATEGORIES: { value: ProductFeedbackCategory; label: string; description: string; icon: React.ReactNode }[] = [
  { value: "bug", label: "Something isn't working", description: "Report a technical or usability problem", icon: <Bug size={18} /> },
  { value: "content", label: "Content issue", description: "Flag a passage, citation, or source problem", icon: <ShieldCheck size={18} /> },
  { value: "feature", label: "Feature idea", description: "Suggest a way TheoCorpus could improve", icon: <Lightbulb size={18} /> },
  { value: "general", label: "General feedback", description: "Share anything else on your mind", icon: <MessageSquareText size={18} /> },
];

export function FeedbackPage() {
  const { token } = useAppContext();
  const contextRaw = useSyncExternalStore(subscribeFeedbackContext, readFeedbackContextRaw, () => null);
  const context = useMemo(() => parseFeedbackContext(contextRaw), [contextRaw]);
  const [categoryOverride, setCategoryOverride] = useState<ProductFeedbackCategory | null>(null);
  const category = categoryOverride ?? context?.category ?? "general";
  const [message, setMessage] = useState("");
  const [contactAllowed, setContactAllowed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reference, setReference] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || pending || message.trim().length < 10) return;
    setPending(true);
    setError(null);
    try {
      const response = await submitProductFeedback(token, {
        category,
        message: message.trim(),
        contact_allowed: contactAllowed,
        route: context?.route ?? "/feedback",
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        search_id: context?.search_id,
        chunk_id: context?.chunk_id,
        document_id: context?.document_id,
        error_code: context?.error_code,
      });
      setReference(response.feedback_id);
      clearFeedbackContext();
      trackFeedbackSubmitted({ category, origin: context?.origin ?? "navigation" });
    } catch {
      setError("Your feedback couldn't be sent. Please try again.");
    } finally {
      setPending(false);
    }
  }

  if (reference) {
    return (
      <div className="mx-auto flex h-full max-w-xl flex-col items-center justify-center px-6 text-center">
        <CheckCircle2 size={34} className="mb-4 text-brand-accent" aria-hidden="true" />
        <h1 className="text-2xl font-semibold text-brand-primary">Thank you for helping improve TheoCorpus</h1>
        <p className="mt-3 text-sm leading-relaxed text-brand-muted">Your report was received. Reference: <span className="font-mono text-brand-primary">{reference.slice(0, 8)}</span></p>
      <button type="button" onClick={() => { setReference(null); setMessage(""); setContactAllowed(false); setCategoryOverride(null); }} className="mt-6 rounded-md border border-brand-accent px-4 py-2 text-sm text-brand-accent hover:bg-brand-accent hover:text-brand-bg">Send another</button>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-2xl px-5 py-8 sm:px-8">
        <h1 className="text-2xl font-semibold text-brand-primary">Feedback &amp; bug reports</h1>
        <p className="mt-2 text-sm leading-relaxed text-brand-muted">Tell us what happened or what would make TheoCorpus more useful. Reports go directly into the product review queue.</p>
        {context && context.origin !== "navigation" && (
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-md border border-brand-accent/30 bg-brand-surface px-4 py-3 text-sm text-brand-muted">
            <span>Relevant app context will be attached securely. Your search text and passage text are not included.</span>
            <button type="button" onClick={clearFeedbackContext} className="shrink-0 text-xs font-medium text-brand-accent hover:underline">Remove attached context</button>
          </div>
        )}
        <form data-ph-no-capture onSubmit={handleSubmit} className="mt-7 space-y-6">
          <fieldset>
            <legend className="mb-3 text-sm font-medium text-brand-primary">What kind of feedback is this?</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {CATEGORIES.map((item) => (
                <label key={item.value} className={`flex cursor-pointer gap-3 rounded-md border p-3 focus-within:outline-none focus-within:ring-2 focus-within:ring-brand-accent ${category === item.value ? "border-brand-accent bg-brand-accent/10" : "border-brand-muted/25 bg-brand-surface"}`}>
                  <input className="sr-only" type="radio" name="category" value={item.value} checked={category === item.value} onChange={() => setCategoryOverride(item.value)} />
                  <span className="mt-0.5 text-brand-accent">{item.icon}</span>
                  <span><span className="block text-sm font-medium text-brand-primary">{item.label}</span><span className="mt-0.5 block text-xs text-brand-muted">{item.description}</span></span>
                </label>
              ))}
            </div>
          </fieldset>
          <label className="block">
            <span className="text-sm font-medium text-brand-primary">Details</span>
            <span className="mt-1 block text-xs text-brand-muted">Please avoid passwords, payment information, or other sensitive personal details.</span>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} minLength={10} maxLength={5000} required rows={8} placeholder="What happened, what did you expect, or what would you like to see?" className="mt-3 w-full resize-y rounded-md border border-brand-muted/30 bg-brand-surface p-3 text-sm text-brand-primary outline-none placeholder:text-brand-muted focus:border-brand-accent focus:ring-1 focus:ring-brand-accent" />
            <span className="mt-1 block text-right text-xs text-brand-muted">{message.length}/5000</span>
          </label>
          <label className="flex items-start gap-3 rounded-md bg-brand-surface p-3 text-sm text-brand-muted">
            <input type="checkbox" checked={contactAllowed} onChange={(event) => setContactAllowed(event.target.checked)} className="mt-0.5 accent-brand-accent" />
            <span>You may contact me at the email connected to my account if you need more information.</span>
          </label>
          {error && <div role="alert" className="rounded-md border border-brand-danger/40 bg-brand-danger/10 px-4 py-3 text-sm text-brand-danger">{error} Your draft has been kept.</div>}
          <button type="submit" disabled={pending || message.trim().length < 10} className="min-h-11 w-full rounded-md bg-brand-accent px-4 py-2 font-medium text-brand-bg hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto">{pending ? "Sending…" : "Send feedback"}</button>
        </form>
      </div>
    </div>
  );
}
