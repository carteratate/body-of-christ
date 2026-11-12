/**
 * The small muted label above a passage that states a position its document rejects
 * (`voice: "rejected"`, corpus cleanup 2.4d): "Condemned proposition 10", "Objection 2".
 * It sits outside the passage text, so the text stays as written. Tokens only, so both
 * themes take it as they are.
 */
export function RejectedLabel({ label, className = "" }: { label: string; className?: string }) {
  return (
    <p className={`text-xs font-semibold tracking-wide text-brand-muted ${className}`}>
      {label}
    </p>
  );
}
