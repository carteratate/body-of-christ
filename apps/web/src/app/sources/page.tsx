import { SourcesPage } from "@/components/sources/SourcesPage";
import { ErrorBoundary } from "@/components/common";

export default function SourcesRoute() {
  return (
    <ErrorBoundary>
      <SourcesPage />
    </ErrorBoundary>
  );
}
