import { ResultsSkeleton } from "@/components/search/ResultsSkeleton";

export default function SearchLoading() {
  return (
    <div className="px-4 pt-4">
      <ResultsSkeleton count={4} />
    </div>
  );
}
