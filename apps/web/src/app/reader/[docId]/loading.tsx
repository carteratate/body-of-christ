export default function ReaderLoading() {
  return (
    <div className="flex flex-col h-full animate-pulse">
      <div className="h-12 bg-brand-surface border-b border-brand-surface/50" />
      <div className="flex-1 px-6 py-6 max-w-3xl w-full mx-auto space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-24 rounded bg-brand-surface" />
        ))}
      </div>
    </div>
  );
}
