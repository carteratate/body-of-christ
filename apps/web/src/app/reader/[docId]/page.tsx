import { AppShell } from "@/components/layout/AppShell";
import { DocumentReader } from "@/components/reader/DocumentReader";

interface PageProps {
  params: Promise<{ docId: string }>;
}

export default async function ReaderRoute({ params }: PageProps) {
  const { docId } = await params;
  return (
    <AppShell>
      <DocumentReader docId={docId} />
    </AppShell>
  );
}
