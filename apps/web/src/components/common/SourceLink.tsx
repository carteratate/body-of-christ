import { ExternalLink } from "lucide-react";

/** The rights holder's credit line, placed right after an excerpt-only passage. */
export function SourceCredit({ text }: { text: string }) {
  return <p className="mt-2 text-xs leading-snug text-brand-muted">{text}</p>;
}

/** Takes the place of "Open in Context" for an excerpt-only document (issue #265):
 *  the passage is shown here, the full text is read at its official source. */
export function SourceLink({ href, className = "" }: { href: string; className?: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${className}`}
    >
      Read the full text at the source
      <ExternalLink size={12} aria-hidden="true" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}
