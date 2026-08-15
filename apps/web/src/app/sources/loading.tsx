export default function SourcesLoading() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-5 sm:px-6 sm:py-6" aria-busy="true" aria-live="polite">
      <h1 className="text-2xl font-semibold text-brand-primary">Library</h1>
      <p className="mb-6 mt-1 text-sm text-brand-muted">Loading the Library…</p>
      <div className="animate-pulse space-y-8" aria-hidden="true">
        {[0, 1, 2, 3].map((section) => (
          <div key={section} className="space-y-2">
            <div className="h-5 w-40 rounded bg-brand-surface" />
            {[0, 1, 2].map((row) => <div key={row} className="h-10 rounded bg-brand-surface" />)}
          </div>
        ))}
      </div>
    </div>
  );
}
