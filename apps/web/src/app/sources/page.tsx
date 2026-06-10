import { AppShell } from "@/components/layout/AppShell";
import { SourcesPage } from "@/components/sources/SourcesPage";
import { ErrorBoundary } from "@/components/common";

export default function SourcesRoute() {
  return (
    <AppShell>
      <ErrorBoundary>
        <SourcesPage />
      </ErrorBoundary>
    </AppShell>
  );
}
