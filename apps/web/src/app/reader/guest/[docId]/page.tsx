import { DocumentReader } from "@/components/reader/DocumentReader";
import { ErrorBoundary } from "@/components/common";

export default async function GuestReaderRoute({ params, searchParams }: { params: Promise<{ docId: string }>; searchParams: Promise<{ anchor?: string; chapter?: string }> }) {
  const { docId } = await params;
  const query = await searchParams;
  const initialMode = query.anchor || query.chapter ? "chapter" : "overview";
  return <ErrorBoundary><DocumentReader docId={docId} isGuest initialMode={initialMode} /></ErrorBoundary>;
}
