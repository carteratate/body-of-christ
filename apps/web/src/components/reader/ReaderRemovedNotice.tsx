import type { ReactNode } from "react";
import { NavPendingBar } from "@/components/common";
import { RemovalNotice } from "@/components/common/PassageFacts";
import type { Tombstone } from "@/lib/corpus-lifecycle";

/** What the reader shows for a removed document or passage (2.4a: 410 with its
 *  tombstone): what was there and why it left, with no text. */
export function ReaderRemovedNotice({ tombstone, header, onBack, backPending, isGuest = false }: {
  tombstone: Tombstone;
  header: ReactNode;
  onBack: () => void;
  backPending: boolean;
  isGuest?: boolean;
}) {
  const byline = [tombstone.author, tombstone.reference !== tombstone.title ? tombstone.reference : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="flex h-full flex-col bg-brand-bg">
      {header}
      <div className="flex-1 overflow-y-auto">
        <main role="status" className="mx-auto w-full max-w-xl px-6 py-10">
          <button type="button" onClick={onBack} aria-busy={backPending || undefined} className="relative mb-6 text-sm text-brand-muted hover:text-brand-accent">
            ← Back<NavPendingBar pending={backPending} />
          </button>
          <section className="rounded-lg border border-brand-muted/20 bg-brand-surface p-5 sm:p-7">
            {tombstone.title && (
              <h1 className="font-brand text-2xl font-semibold text-brand-accent">{tombstone.title}</h1>
            )}
            {byline && <p className="mt-1 text-sm text-brand-muted">{byline}</p>}
            <RemovalNotice tombstone={tombstone} isGuest={isGuest} className="mt-5" />
          </section>
        </main>
      </div>
    </div>
  );
}
