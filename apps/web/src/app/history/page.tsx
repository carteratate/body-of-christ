import { AppShell } from "@/components/layout/AppShell";
import { ErrorBoundary } from "@/components/common";
import { HistoryPage } from "@/components/history";

export default function HistoryRoute() {
  return (
    <AppShell>
      <ErrorBoundary>
        <HistoryPage />
      </ErrorBoundary>
    </AppShell>
  );
}
