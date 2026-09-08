import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-brand-bg px-4 text-brand-primary">
      <div className="w-full max-w-md rounded-xl border border-brand-muted/20 bg-brand-surface p-6 text-center">
        <p className="font-brand text-sm uppercase tracking-[0.2em] text-brand-accent">TheoCorpus</p>
        <h1 className="mt-3 font-brand text-2xl font-semibold">Page not found</h1>
        <p className="mt-3 text-sm leading-6 text-brand-muted">
          The page may have moved, or the link may be out of date.
        </p>
        <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
          <Link href="/search" className="rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-brand-bg transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
            Go to Search
          </Link>
          <Link href="/sources" className="rounded-md border border-brand-muted/30 px-4 py-2 text-sm font-medium text-brand-primary hover:border-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
            Open Library
          </Link>
        </div>
      </div>
    </main>
  );
}
