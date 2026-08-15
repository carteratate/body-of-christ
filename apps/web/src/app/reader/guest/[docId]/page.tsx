import { GuestShell } from "@/components/layout/GuestShell";
import { DocumentReader } from "@/components/reader/DocumentReader";
import { ErrorBoundary } from "@/components/common";

export default async function GuestReaderRoute({ params }: { params: Promise<{ docId: string }> }) {
  const { docId } = await params;
  return <GuestShell><ErrorBoundary><DocumentReader docId={docId} isGuest /></ErrorBoundary></GuestShell>;
}
