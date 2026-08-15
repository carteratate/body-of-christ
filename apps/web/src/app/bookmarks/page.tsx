import { BookmarksPage } from "@/components/bookmarks/BookmarksPage";
import { ErrorBoundary } from "@/components/common";

export default function BookmarksRoute() {
  return (
    <ErrorBoundary>
      <BookmarksPage />
    </ErrorBoundary>
  );
}
