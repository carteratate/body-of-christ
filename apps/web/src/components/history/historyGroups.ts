import type { SearchSummaryV2 } from "@/lib/api";

export interface HistoryGroup {
  label: "Today" | "Yesterday" | "Earlier";
  searches: SearchSummaryV2[];
}

function localDayStart(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function groupSearchesByLocalDate(
  searches: SearchSummaryV2[],
  now = new Date(),
): HistoryGroup[] {
  const todayStart = localDayStart(now);
  const yesterdayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1).getTime();
  const groups: HistoryGroup[] = [
    { label: "Today", searches: [] },
    { label: "Yesterday", searches: [] },
    { label: "Earlier", searches: [] },
  ];

  for (const search of searches) {
    const created = new Date(search.created_at).getTime();
    if (created >= todayStart) groups[0].searches.push(search);
    else if (created >= yesterdayStart) groups[1].searches.push(search);
    else groups[2].searches.push(search);
  }

  return groups.filter((group) => group.searches.length > 0);
}
