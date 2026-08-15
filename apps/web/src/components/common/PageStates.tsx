"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const PAGE_NAMES: Array<[string, string]> = [
  ["/sources", "Library"],
  ["/bookmarks", "Saved Passages"],
  ["/history", "Search History"],
  ["/discover", "Source Guide"],
  ["/settings", "Settings"],
  ["/feedback", "Feedback"],
  ["/about", "About TheoCorpus"],
  ["/reader", "Document"],
  ["/signup", "Create Account"],
  ["/login", "Sign In"],
  ["/update-password", "Password Reset"],
  ["/search", "Search"],
];

function pageName(pathname: string): string {
  return PAGE_NAMES.find(([prefix]) => pathname.startsWith(prefix))?.[1] ?? "TheoCorpus";
}

export function PageLoadingState() {
  const pathname = usePathname();
  const name = pageName(pathname);

  return (
    <div className="flex min-h-full flex-1 bg-brand-bg text-brand-primary" aria-busy="true" aria-live="polite">
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
        <div className="mb-7">
          <p className="font-brand text-xl font-semibold text-brand-accent">TheoCorpus</p>
          <p className="mt-2 text-sm text-brand-muted">Loading {name}…</p>
        </div>
        <div className="animate-pulse space-y-4" aria-hidden="true">
          <div className="h-8 w-48 rounded bg-brand-surface" />
          <div className="h-12 w-full rounded-md bg-brand-surface" />
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-24 rounded-md bg-brand-surface" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function PageErrorState({ reset }: { reset: () => void }) {
  const pathname = usePathname();
  const name = pageName(pathname);
  const isGuest = pathname.startsWith("/search/guest") || pathname.startsWith("/reader/guest");
  const isPublic = pathname === "/" || pathname === "/login" || pathname === "/signup" || pathname === "/update-password" || pathname === "/onboarding-preview";
  const recoveryHref = isGuest ? "/search/guest" : isPublic ? "/" : "/search";
  const recoveryLabel = isGuest ? "Back to Guest Search" : isPublic ? "Back to TheoCorpus" : "Go to Search";

  return (
    <div className="flex min-h-full flex-1 items-center justify-center bg-brand-bg px-4 text-brand-primary">
      <div className="w-full max-w-md rounded-xl border border-brand-muted/20 bg-brand-surface p-6 text-center">
        <h1 className="font-brand text-xl font-semibold">We couldn&apos;t open {name}</h1>
        <p className="mt-3 text-sm leading-6 text-brand-muted">
          This may be a temporary connection problem. Try loading the page again.
        </p>
        <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
          <button
            type="button"
            onClick={reset}
            className="rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-brand-bg transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            Try again
          </button>
          <Link
            href={recoveryHref}
            className="rounded-md border border-brand-muted/30 px-4 py-2 text-sm font-medium text-brand-primary hover:border-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            {recoveryLabel}
          </Link>
        </div>
      </div>
    </div>
  );
}
