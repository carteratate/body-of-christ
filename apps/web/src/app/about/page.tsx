import { AboutPage } from "@/components/about/AboutPage";
import { ErrorBoundary } from "@/components/common";

export const metadata = { title: "About — TheoCorpus" };

export default function AboutRoute() {
  return (
    <ErrorBoundary>
      <AboutPage />
    </ErrorBoundary>
  );
}
