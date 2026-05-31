import { AppShell } from "@/components/layout/AppShell";
import { DocumentReader } from "@/components/reader/DocumentReader";
import { ErrorBoundary } from "@/components/common";

interface PageProps {
  params: Promise<{ docId: string }>;
}

export default async function ReaderRoute({ params }: PageProps) {
  const { docId } = await params;
  return (
    <AppShell>
      <ErrorBoundary>
        <DocumentReader docId={docId} />
      </ErrorBoundary>
    </AppShell>
  );
}
