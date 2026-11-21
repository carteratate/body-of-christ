import { SourceSitesPage } from "@/components/about/SourceSitesPage";

export const metadata = { title: "Sources — TheoCorpus" };

export default function GuestSourcesAboutRoute() {
  return <SourceSitesPage isGuest />;
}
