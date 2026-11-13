import type { ReactNode } from "react";

/**
 * A passage that states a position its document rejects (`voice: "rejected"`, corpus
 * cleanup 2.4d), set off as someone else's words: a muted caption above naming whose
 * position it is ("Condemned proposition 10 · a position the document rejects"), and
 * the text as a quotation, with a rule down its left side and in italics. Shown only
 * where the passage text is shown, never in a collapsed header (Carter, 12 Nov 2026).
 *
 * With no label it renders its children untouched, so every other passage is as before.
 * Tokens only, so both themes take it as they are.
 */
export function RejectedVoice({ label, children }: { label: string | null; children: ReactNode }) {
  if (!label) return <>{children}</>;
  return (
    <>
      <p className="mb-1 text-xs text-brand-muted">
        <span className="font-semibold">{label}</span> · a position the document rejects
      </p>
      <div className="border-l-2 border-brand-muted/60 pl-3 italic" data-voice="rejected">
        {children}
      </div>
    </>
  );
}

/** The muted caption above an opened passage naming its role in its document
 *  ("Objection 1", "Reply to Objection 2"), for a passage that is not a rejected voice. */
export function RoleCaption({ role }: { role: string }) {
  return <p className="mb-1 text-xs font-semibold text-brand-muted">{role}</p>;
}
