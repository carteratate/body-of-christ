import { ChevronLeft, ExternalLink } from "lucide-react";
import { IntentLink } from "@/components/common/NavPending";
import { getCollectionMeta } from "@/lib/collections";
import { SOURCE_SITES, type SourceSite } from "@/lib/source-sites";

/**
 * About › Sources (corpus cleanup 4.4): each site the corpus takes text from, what is
 * taken, on what basis, and the documents. "Sourced via CCEL.org" and the like are not
 * on the result card (4.4, rule 4); they are here and on each document's overview. The
 * data is generated from the rights inventory (`datapipeline/scripts/source_sites.py`).
 */
export function SourceSitesPage({ isGuest = false }: { isGuest?: boolean }) {
  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
        <IntentLink
          href={isGuest ? "/guest/about" : "/about"}
          className="mb-4 inline-flex items-center gap-1 text-xs text-brand-muted hover:text-brand-primary"
        >
          <ChevronLeft size={14} aria-hidden="true" /> About
        </IntentLink>
        <h1 className="mb-2 text-2xl font-semibold text-brand-primary">Sources</h1>
        <p className="mb-6 text-sm leading-relaxed text-brand-muted">
          Where TheoCorpus takes its texts from, and on what basis. Each document&apos;s
          overview in the reader names its source too. The notices rights holders require
          are shown with every passage.
        </p>
        <div className="space-y-4">
          {SOURCE_SITES.map((site) => <SiteSection key={site.key} site={site} />)}
        </div>
      </div>
    </div>
  );
}

function SiteSection({ site }: { site: SourceSite }) {
  const count = site.documents.length;
  return (
    <section className="rounded-lg bg-brand-surface px-4 py-4" aria-labelledby={`site-${site.key}`} data-testid="source-site">
      <h2 id={`site-${site.key}`} className="text-base font-semibold text-brand-primary">
        <a
          href={site.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 hover:text-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          {site.name}
          <ExternalLink size={13} aria-hidden="true" />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-brand-primary">{site.taken}</p>
      <div className="mt-2 space-y-0.5 text-xs leading-snug text-brand-muted">
        {site.basis.map((basis) => <p key={basis}>{basis}</p>)}
        {site.excerpt_bases.map((basis) => (
          <p key={basis.statement}>
            {basis.documents === 1 ? "1 document is" : `${basis.documents.toLocaleString()} documents are`}{" "}
            quoted in excerpts on the basis of{" "}
            {basis.url ? (
              <a href={basis.url} target="_blank" rel="noopener noreferrer" className="text-brand-primary underline underline-offset-2">
                {basis.statement}<span className="sr-only"> (opens in a new tab)</span>
              </a>
            ) : basis.statement}
            .
          </p>
        ))}
      </div>
      <details className="mt-3 group">
        <summary className="cursor-pointer text-xs font-medium text-brand-primary underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
          {count === 1 ? "1 document" : `${count.toLocaleString()} documents`}
        </summary>
        <ul className="mt-2 space-y-1 text-xs leading-snug">
          {site.documents.map((doc) => (
            <li key={doc.document_id}>
              <span className="text-brand-primary">{doc.title}</span>
              <span className="ml-2 text-brand-muted">{getCollectionMeta(doc.collection)?.label ?? doc.collection}</span>
              {doc.texts?.map((text) => <span key={text} className="block text-brand-muted">{text}</span>)}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
