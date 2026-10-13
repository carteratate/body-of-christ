"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ChevronRight } from "lucide-react";
import type { ContentsNode } from "@/lib/api";
import {
  ancestorKeys,
  indexContents,
  matchingKeys,
  opensOwnContent,
  visibleRows,
  type VisibleRow,
} from "@/lib/contents-tree";

const FILTER_LIMIT = 200;

function rowElement(tree: HTMLElement | null, key: string): HTMLElement | undefined {
  return [...(tree?.querySelectorAll<HTMLElement>("[data-node-key]") ?? [])]
    .find((element) => element.dataset.nodeKey === key);
}

interface Props {
  nodes: ContentsNode[];
  /** Node to mark as the reader's place; its ancestors start expanded. */
  currentKey?: string | null;
  /** Nodes whose ancestors and selves start expanded. */
  initiallyExpanded?: string[];
  /** Controlled filter text; empty shows the tree as expanded. */
  filter?: string;
  /** Scroll the current node into view within the nearest scroll container on mount. */
  scrollCurrentIntoView?: boolean;
  onOpen: (node: ContentsNode) => void;
}

/**
 * A document's contents tree (issue #251), as an ARIA tree. Rows render only for
 * expanded branches, so the Summa's ~3,700 nodes cost nothing until opened.
 *
 * Choosing a row opens its node, except a node that only groups its children (a Part
 * opens the same place as its first article): choosing that expands or collapses it.
 * The chevron always expands or collapses.
 */
export function ContentsTree({
  nodes,
  currentKey = null,
  initiallyExpanded = [],
  filter = "",
  scrollCurrentIntoView = false,
  onOpen,
}: Props) {
  const index = useMemo(() => indexContents(nodes), [nodes]);
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const open = new Set<string>();
    for (const key of initiallyExpanded) {
      if (!index.has(key)) continue;
      open.add(key);
      for (const ancestor of ancestorKeys(index, key)) open.add(ancestor);
    }
    if (currentKey && index.has(currentKey)) {
      for (const ancestor of ancestorKeys(index, currentKey)) open.add(ancestor);
    }
    return open;
  });
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const treeRef = useRef<HTMLDivElement | null>(null);

  // Expand to the reader's place when it moves (the in-reader panel follows scrolling).
  const [shownCurrent, setShownCurrent] = useState(currentKey);
  if (currentKey !== shownCurrent) {
    setShownCurrent(currentKey);
    if (currentKey && index.has(currentKey)) {
      const missing = ancestorKeys(index, currentKey).filter((key) => !expanded.has(key));
      if (missing.length) setExpanded(new Set([...expanded, ...missing]));
    }
  }

  const matches = useMemo(() => (filter.trim() ? matchingKeys(index, filter) : null), [filter, index]);
  const { rows, truncated } = useMemo(
    () => visibleRows(nodes, index, expanded, matches, FILTER_LIMIT),
    [expanded, index, matches, nodes],
  );

  const activeKey = rows.some((row) => row.node.key === focusKey)
    ? focusKey
    : rows.find((row) => row.node.key === currentKey)?.node.key ?? rows[0]?.node.key ?? null;

  useEffect(() => {
    if (!scrollCurrentIntoView || !currentKey) return;
    rowElement(treeRef.current, currentKey)?.scrollIntoView({ block: "nearest" });
    // Only on mount and when the reader's place moves, never on expansion changes.
  }, [currentKey, scrollCurrentIntoView]);

  function toggle(key: string, open?: boolean) {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (open ?? !next.has(key)) next.add(key);
      else next.delete(key);
      return next;
    });
  }

  function choose(row: VisibleRow) {
    setFocusKey(row.node.key);
    if (matches || opensOwnContent(row.node)) onOpen(row.node);
    else toggle(row.node.key);
  }

  function focusRow(key: string | null | undefined) {
    if (!key) return;
    setFocusKey(key);
    rowElement(treeRef.current, key)?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const position = rows.findIndex((row) => row.node.key === activeKey);
    const row = rows[position];
    if (!row) return;
    const hasChildren = row.node.children.length > 0;
    switch (event.key) {
      case "ArrowDown": focusRow(rows[position + 1]?.node.key); break;
      case "ArrowUp": focusRow(rows[position - 1]?.node.key); break;
      case "Home": focusRow(rows[0]?.node.key); break;
      case "End": focusRow(rows[rows.length - 1]?.node.key); break;
      case "ArrowRight":
        if (hasChildren && !row.expanded && !matches) toggle(row.node.key, true);
        else if (hasChildren && row.expanded) focusRow(rows[position + 1]?.node.key);
        break;
      case "ArrowLeft":
        if (hasChildren && row.expanded && !matches) toggle(row.node.key, false);
        else focusRow(row.parentKey);
        break;
      case "Enter":
      case " ":
        choose(row);
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  return (
    <div>
      <div ref={treeRef} role="tree" aria-label="Contents" onKeyDown={onKeyDown} className="min-w-0">
        {rows.map((row) => {
          const { node } = row;
          const hasChildren = node.children.length > 0;
          const current = node.key === currentKey;
          return (
            <div
              key={node.key}
              data-node-key={node.key}
              role="treeitem"
              aria-level={row.level}
              aria-setsize={row.setSize}
              aria-posinset={row.posInSet}
              aria-expanded={hasChildren ? row.expanded : undefined}
              aria-current={current ? "location" : undefined}
              aria-selected={current}
              tabIndex={node.key === activeKey ? 0 : -1}
              onClick={() => choose(row)}
              onFocus={() => setFocusKey(node.key)}
              className={`group flex min-h-11 min-w-0 cursor-pointer items-start gap-1 rounded-md py-2 pr-2 text-left transition-colors hover:bg-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${current ? "text-brand-accent" : "text-brand-primary"}`}
              style={{ paddingLeft: `${(row.level - 1) * 1.25}rem` }}
            >
              <span
                aria-hidden="true"
                onClick={(event) => {
                  if (!hasChildren || matches) return;
                  event.stopPropagation();
                  setFocusKey(node.key);
                  toggle(node.key);
                }}
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded text-brand-muted ${hasChildren ? "hover:text-brand-accent" : "invisible"}`}
              >
                <ChevronRight size={16} className={`transition-transform ${row.expanded ? "rotate-90" : ""}`} />
              </span>
              <span className="min-w-0 flex-1 pt-1">
                <span className={`block text-sm leading-snug ${row.level === 1 ? "font-semibold" : ""} ${row.matched ? "underline decoration-brand-accent/60 underline-offset-4" : ""}`}>
                  {node.short_label}
                </span>
                {node.range_label && (
                  <span className="mt-0.5 block text-xs text-brand-muted">{node.range_label}</span>
                )}
              </span>
            </div>
          );
        })}
      </div>
      {matches && rows.length === 0 && (
        <p className="px-2 py-6 text-center text-sm text-brand-muted">Nothing in the contents matches that search.</p>
      )}
      {truncated && (
        <p className="px-2 pt-3 text-center text-xs text-brand-muted">
          Showing the first {FILTER_LIMIT} matches. Refine your search to see the rest.
        </p>
      )}
    </div>
  );
}
