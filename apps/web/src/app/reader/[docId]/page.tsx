import { DocumentReader } from "@/components/reader/DocumentReader";
import { ErrorBoundary } from "@/components/common";

interface PageProps {
  params: Promise<{ docId: string }>;
  searchParams: Promise<{ anchor?: string; chapter?: string }>;
}

export default async function ReaderRoute({ params, searchParams }: PageProps) {
  const { docId } = await params;
  const query = await searchParams;
  const initialMode = query.anchor || query.chapter ? "chapter" : "overview";
  return (
    <ErrorBoundary>
      <DocumentReader docId={docId} initialMode={initialMode} />
    </ErrorBoundary>
  );
}
