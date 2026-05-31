import { AppShell } from "@/components/layout/AppShell";
import { SearchPage } from "@/components/search/SearchPage";
import { ErrorBoundary } from "@/components/common";

export default function SearchRoute() {
  return (
    <AppShell>
      <ErrorBoundary>
        <SearchPage />
      </ErrorBoundary>
    </AppShell>
  );
}
