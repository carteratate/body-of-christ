import { SearchPage } from "@/components/search/SearchPage";

export const metadata = {
  title: "TheoCorpus — Try a Search",
};

export default function GuestSearchPage() {
  return <SearchPage isGuest />;
}
