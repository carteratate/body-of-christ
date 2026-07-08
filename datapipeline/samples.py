"""Isolated sample output for --sample runs: timestamped JSONL + stdout preview."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone


class SampleWriter:
    def __init__(self, collection: str, out_dir: str) -> None:
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        self.path = os.path.join(out_dir, f"{collection}-{ts}.jsonl")

    def write(self, record: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def preview(self, merged, passage) -> str:
        lines = [
            "━" * 3 + f" {passage.reference} " + "━" * 20,
            f"Content:    {passage.content[:120]}",
            "",
            "── Facets " + "─" * 20,
        ]
        for i, f in enumerate(merged.facets, 1):
            lines.append(f"[{i}] {f.kind} | {f.confidence}")
            lines.append(f"    TEXT: {f.text}")
            lines.append(f"    Q:    {f.question}")
        lines.append("── Annotation " + "─" * 20)
        lines.append(merged.annotation)
        lines.append("━" * 40)
        return "\n".join(lines)
