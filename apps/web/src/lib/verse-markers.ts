import { type ReactNode, createElement } from "react";

const VERSE_MARKER_RE = /\{\{v:(\d+)\}\}/;
const VERSE_MARKER_STRIP_RE = /\{\{v:\d+\}\}\s*/g;

export function stripVerseMarkers(text: string): string {
  return text.replace(VERSE_MARKER_STRIP_RE, "");
}

export function renderVerseMarkers(content: string): ReactNode[] {
  const parts = content.split(VERSE_MARKER_RE);
  const nodes: ReactNode[] = [];
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 1) {
      nodes.push(
        createElement(
          "sup",
          {
            key: `v${i}`,
            className: "text-brand-muted mr-1",
            style: { fontSize: 10 },
          },
          parts[i],
        ),
      );
    } else if (parts[i]) {
      nodes.push(parts[i]);
    }
  }
  return nodes;
}
