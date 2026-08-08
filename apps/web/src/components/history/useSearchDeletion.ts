"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { deleteSearch, type SearchSummaryV2 } from "@/lib/api";
import { useAppContext } from "@/components/layout/AppShell";
import { trackSearchDeleted } from "@/lib/analytics";

interface SearchDeletionOptions {
  searches: SearchSummaryV2[];
  removeLocally: (id: string) => void;
  restoreLocally: (search: SearchSummaryV2, index: number) => void;
  onSuccess?: (id: string) => void;
  showToast: (message: string, type?: "success" | "error") => void;
  origin?: "sidebar" | "history_page";
  focusAfterRemove?: (index: number) => void;
  focusAfterRestore?: (id: string) => void;
}

export function useSearchDeletion({
  searches,
  removeLocally,
  restoreLocally,
  onSuccess,
  showToast,
  origin = "history_page",
  focusAfterRemove,
  focusAfterRestore,
}: SearchDeletionOptions) {
  const router = useRouter();
  const { token, activeSearchId, newSearch } = useAppContext();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function deleteById(id: string) {
    if (!token || deletingId) return;
    const index = searches.findIndex((search) => search.id === id);
    const removed = searches[index];
    if (!removed) return;

    setDeletingId(id);
    removeLocally(id);
    focusAfterRemove?.(index);
    try {
      await deleteSearch(token, id);
      trackSearchDeleted({ surface: origin });
      onSuccess?.(id);
      if (id === activeSearchId) {
        router.push("/search");
        newSearch();
      }
      showToast("Search deleted.", "success");
    } catch {
      restoreLocally(removed, index);
      focusAfterRestore?.(id);
      showToast("Couldn't delete search. Restored.", "error");
    } finally {
      setDeletingId(null);
    }
  }

  return { deletingId, deleteById };
}
