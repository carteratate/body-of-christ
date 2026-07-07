import { AppShell } from "@/components/layout/AppShell";
import { AboutPage } from "@/components/about/AboutPage";
import { ErrorBoundary } from "@/components/common";

export const metadata = { title: "About — TheoCorpus" };

export default function AboutRoute() {
  return (
    <AppShell>
      <ErrorBoundary>
        <AboutPage />
      </ErrorBoundary>
    </AppShell>
  );
}
