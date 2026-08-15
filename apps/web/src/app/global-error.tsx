"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-brand-bg text-brand-primary">
        <main className="flex min-h-screen items-center justify-center px-4">
          <div className="w-full max-w-md rounded-xl border border-brand-muted/20 bg-brand-surface p-6 text-center">
            <h1 className="text-xl font-semibold">TheoCorpus couldn&apos;t open</h1>
            <p className="mt-3 text-sm leading-6 text-brand-muted">
              Your work is still safe. Try loading TheoCorpus again.
            </p>
            <button type="button" onClick={reset} className="mt-6 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-brand-bg">
              Try again
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
