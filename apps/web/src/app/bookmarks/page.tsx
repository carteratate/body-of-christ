import { AppShell } from "@/components/layout/AppShell";
import { BookmarksPage } from "@/components/bookmarks/BookmarksPage";

export default function BookmarksRoute() {
  return (
    <AppShell>
      <BookmarksPage />
    </AppShell>
  );
}
