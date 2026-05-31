import { ResultsSkeleton } from "@/components/search/ResultsSkeleton";

export default function BookmarksLoading() {
  return (
    <div className="px-6 py-6 max-w-3xl w-full mx-auto">
      <div className="h-8 w-40 rounded bg-brand-surface animate-pulse mb-6" />
      <ResultsSkeleton count={3} />
    </div>
  );
}
