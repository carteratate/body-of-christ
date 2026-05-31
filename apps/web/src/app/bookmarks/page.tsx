import { AppShell } from "@/components/layout/AppShell";
import { BookmarksPage } from "@/components/bookmarks/BookmarksPage";
import { ErrorBoundary } from "@/components/common";

export default function BookmarksRoute() {
  return (
    <AppShell>
      <ErrorBoundary>
        <BookmarksPage />
      </ErrorBoundary>
    </AppShell>
  );
}
