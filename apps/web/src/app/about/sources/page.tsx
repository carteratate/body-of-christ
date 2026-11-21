import { SourceSitesPage } from "@/components/about/SourceSitesPage";
import { ErrorBoundary } from "@/components/common";

export const metadata = { title: "Sources — TheoCorpus" };

export default function SourcesAboutRoute() {
  return (
    <ErrorBoundary>
      <SourceSitesPage />
    </ErrorBoundary>
  );
}
