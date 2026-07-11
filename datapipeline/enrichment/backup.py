"""Append-only JSONL backup of every Opus enrichment output, written BEFORE any DB write."""
from __future__ import annotations

import glob
import json
import os
from collections.abc import Iterator
from datetime import datetime, timezone


class Backup:
    def __init__(self, dir_path: str) -> None:
        self.dir_path = dir_path
        os.makedirs(dir_path, exist_ok=True)

    def write(self, collection: str, record: dict) -> None:
        record = dict(record)
        record.setdefault("ts", datetime.now(timezone.utc).isoformat())
        path = os.path.join(self.dir_path, f"{collection}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def import_backup(path_or_dir: str) -> Iterator[dict]:
    if os.path.isdir(path_or_dir):
        paths = sorted(glob.glob(os.path.join(path_or_dir, "*.jsonl")))
    else:
        paths = [path_or_dir]
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
