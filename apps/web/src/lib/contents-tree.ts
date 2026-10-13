// Pure logic for a document's contents tree (issue #251): indexing, filtering and the
// rows a tree shows for a given expansion. ContentsTree renders what this returns.

import type { ContentsNode } from "@/lib/api";

/** Case- and accent-insensitive form used for matching. */
export function normalizeForSearch(value: string): string {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

export interface IndexedNode {
  node: ContentsNode;
  parentKey: string | null;
  level: number;      // 1-based, as aria-level
  posInSet: number;   // 1-based among siblings
  setSize: number;
}

export type ContentsIndex = Map<string, IndexedNode>;

export function indexContents(nodes: ContentsNode[]): ContentsIndex {
  const index: ContentsIndex = new Map();
  const visit = (siblings: ContentsNode[], parentKey: string | null, level: number) => {
    siblings.forEach((node, position) => {
      index.set(node.key, { node, parentKey, level, posInSet: position + 1, setSize: siblings.length });
      visit(node.children, node.key, level + 1);
    });
  };
  visit(nodes, null, 1);
  return index;
}

export function ancestorKeys(index: ContentsIndex, key: string): string[] {
  const keys: string[] = [];
  let parent = index.get(key)?.parentKey ?? null;
  while (parent !== null) {
    keys.push(parent);
    parent = index.get(parent)?.parentKey ?? null;
  }
  return keys;
}

/** The deepest node that opens `chapterKey`, if any: the reader's place in the tree. */
export function nodeForChapter(nodes: ContentsNode[], chapterKey: string): ContentsNode | null {
  let found: ContentsNode | null = null;
  const visit = (siblings: ContentsNode[]) => {
    for (const node of siblings) {
      if (node.chapter_key === chapterKey && !node.anchor) found = node;
      visit(node.children);
    }
  };
  visit(nodes);
  return found;
}

/**
 * Whether opening this node shows something its first child does not. A node that only
 * groups its children (a Summa Part opens its first article, exactly as that article's
 * own row does) expands instead of opening when chosen.
 */
export function opensOwnContent(node: ContentsNode): boolean {
  const [first] = node.children;
  if (!first) return true;
  return first.chapter_key !== node.chapter_key || first.anchor !== null;
}

const PARAGRAPH_RANGE = /§§?\s*(\d[\d,]*)(?:\s*[–—-]\s*(\d[\d,]*))?/;

function inParagraphRange(rangeLabel: string | null, paragraph: number): boolean {
  const match = rangeLabel?.match(PARAGRAPH_RANGE);
  if (!match) return false;
  const start = Number(match[1].replaceAll(",", ""));
  const end = match[2] ? Number(match[2].replaceAll(",", "")) : start;
  return paragraph >= start && paragraph <= end;
}

/**
 * Keys of the nodes a filter matches. Text matches the short label, label or range
 * label. A number also matches a node whose paragraph range ("§§1422–1498") holds it;
 * for a tree with paragraph ranges that replaces text matching, so "1471" finds the
 * section holding CCC 1471 rather than every label containing the digits.
 */
export function matchingKeys(index: ContentsIndex, rawFilter: string): Set<string> {
  const term = normalizeForSearch(rawFilter.trim());
  const keys = new Set<string>();
  if (!term) return keys;
  const paragraph = /^\d+$/.test(term) ? Number(term) : null;
  const hasRanges = paragraph !== null
    && [...index.values()].some(({ node }) => PARAGRAPH_RANGE.test(node.range_label ?? ""));
  for (const [key, { node }] of index) {
    const matched = hasRanges
      ? inParagraphRange(node.range_label, paragraph!)
      : [node.short_label, node.label, node.range_label ?? ""]
          .some((text) => normalizeForSearch(text).includes(term));
    if (matched) keys.add(key);
  }
  return keys;
}

export interface VisibleRow extends IndexedNode {
  expanded: boolean;
  matched: boolean;
}

/**
 * The rows a tree shows, in pre-order. Without a filter, a node's children show when it
 * is expanded. With one, only matches and their ancestors show, with every ancestor
 * open, and at most `limit` matches (the result says whether more were cut).
 */
export function visibleRows(
  nodes: ContentsNode[],
  index: ContentsIndex,
  expanded: ReadonlySet<string>,
  matches: Set<string> | null,
  limit = Infinity,
): { rows: VisibleRow[]; truncated: boolean } {
  const rows: VisibleRow[] = [];
  let shownMatches = 0;
  let truncated = false;

  let onPath: Set<string> | null = null;
  if (matches) {
    onPath = new Set();
    for (const key of matches) for (const ancestor of ancestorKeys(index, key)) onPath.add(ancestor);
  }

  const visit = (siblings: ContentsNode[]): boolean => {
    for (const node of siblings) {
      const info = index.get(node.key)!;
      if (onPath) {
        const matched = matches!.has(node.key);
        const leadsToMatch = onPath.has(node.key);
        if (!matched && !leadsToMatch) continue;
        if (matched) {
          if (shownMatches >= limit) { truncated = true; return false; }
          shownMatches += 1;
        }
        rows.push({ ...info, expanded: leadsToMatch, matched });
        if (leadsToMatch && !visit(node.children)) return false;
      } else {
        const open = node.children.length > 0 && expanded.has(node.key);
        rows.push({ ...info, expanded: open, matched: false });
        if (open) visit(node.children);
      }
    }
    return true;
  };
  visit(nodes);
  return { rows, truncated };
}

/** How many articles, sections and so on a tree holds, for a summary line. */
export function countByKind(nodes: ContentsNode[]): Map<string, number> {
  const counts = new Map<string, number>();
  const visit = (siblings: ContentsNode[]) => {
    for (const node of siblings) {
      counts.set(node.kind, (counts.get(node.kind) ?? 0) + 1);
      visit(node.children);
    }
  };
  visit(nodes);
  return counts;
}
