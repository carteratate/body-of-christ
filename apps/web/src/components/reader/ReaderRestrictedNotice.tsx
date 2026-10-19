import type { ReactNode } from "react";
import { NavPendingBar } from "@/components/common";
import { SourceLink } from "@/components/common/SourceLink";

/** What the reader shows for an excerpt-only document (issue #265): its passages are
 *  searchable, but its full text is read at the official source. */
export function ReaderRestrictedNotice({ sourceUrl, header, onBack, backPending }: {
  sourceUrl: string | null;
  header: ReactNode;
  onBack: () => void;
  backPending: boolean;
}) {
  return (
    <div className="flex h-full flex-col bg-brand-bg">
      {header}
      <div role="status" className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="max-w-md text-sm leading-relaxed text-brand-primary">
          The full text of this document isn&apos;t available on TheoCorpus yet.
        </p>
        <p className="max-w-md text-xs leading-relaxed text-brand-muted">
          Its passages still appear in search results.
        </p>
        <div className="flex items-center gap-4">
          <button type="button" onClick={onBack} aria-busy={backPending || undefined} className="relative text-sm text-brand-muted hover:text-brand-accent">
            ← Back<NavPendingBar pending={backPending} />
          </button>
          {sourceUrl && <SourceLink href={sourceUrl} />}
        </div>
      </div>
    </div>
  );
}
