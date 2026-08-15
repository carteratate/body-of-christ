import { ErrorBoundary } from "@/components/common";
import { HistoryPage } from "@/components/history";

export default function HistoryRoute() {
  return (
    <ErrorBoundary>
      <HistoryPage />
    </ErrorBoundary>
  );
}
