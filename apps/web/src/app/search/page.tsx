import { SearchPage } from "@/components/search/SearchPage";
import { ErrorBoundary } from "@/components/common";

export default function SearchRoute() {
  return (
    <ErrorBoundary>
      <SearchPage />
    </ErrorBoundary>
  );
}
