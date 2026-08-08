import { describe, expect, it } from "vitest";
import { groupSearchesByLocalDate } from "./historyGroups";
import type { SearchSummaryV2 } from "@/lib/api";

function search(id: string, createdAt: string): SearchSummaryV2 {
  return { id, query: id, filters: null, result_count: null, created_at: createdAt };
}

describe("groupSearchesByLocalDate", () => {
  it("uses local calendar boundaries rather than elapsed 24-hour windows", () => {
    const now = new Date(2026, 7, 4, 0, 15);
    const lateYesterday = new Date(2026, 7, 3, 23, 55).toISOString();
    const groups = groupSearchesByLocalDate([
      search("today", new Date(2026, 7, 4, 0, 5).toISOString()),
      search("yesterday", lateYesterday),
      search("earlier", new Date(2026, 7, 2, 23, 59).toISOString()),
    ], now);

    expect(groups.map((group) => [group.label, group.searches.map((item) => item.id)])).toEqual([
      ["Today", ["today"]],
      ["Yesterday", ["yesterday"]],
      ["Earlier", ["earlier"]],
    ]);
  });
});
