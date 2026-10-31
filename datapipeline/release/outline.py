"""The stored reader outline against the passages (corpus-cleanup item 0.1d).

`document_chapters` (migration 0037) stores each document's chapter list, which `/toc`,
`/reader`, `/documents/{id}` and `/sources` read instead of deriving it per request. Its
`chunk_count` matched the passages on 6 Oct 2026, but its order and labels had never been
compared with them (synthesis section 5). This compares, offline, the snapshot's
`document_chapters.jsonl` with the outline its passages give, by the rule
`refresh_document_outline` uses and Sol's query states: chapters are the passages' chapter
keys, in the order of each key's first position (ties by key), each labelled with its
first passage's label.

A failure is `release.outline_matches:<collection>/<document_id>` (a remap Failure keyed
by the document ID). A document whose stored `chunk_count` is NULL has no current outline
(the API derives the outline then), so it is not judged. A snapshot without the file
skips the check.
"""
from __future__ import annotations

import json
import os

from model import Document
from release.remap import Failure

CHAPTERS_FILE = "document_chapters.jsonl"
DOCUMENTS_FILE = "documents.jsonl"
DETAILS_LISTED = 5


def derived_outline(document: Document) -> list[tuple[str, str]]:
    """(chapter_key, chapter_label) in reading order, from the passages."""
    firsts: dict[str, tuple[int, str]] = {}
    for p in document.passages:
        if not p.chapter_key:
            continue
        position = p.position if p.position is not None else 1 << 30
        if p.chapter_key not in firsts or position < firsts[p.chapter_key][0]:
            firsts[p.chapter_key] = (position, p.chapter_label)
    ordered = sorted(firsts.items(), key=lambda kv: (kv[1][0], kv[0]))
    return [(key, label) for key, (_, label) in ordered]


def compare(stored: list[dict], document: Document) -> list[str]:
    """The differences between a document's stored outline rows and its derived one."""
    expected = {key: (i, label) for i, (key, label) in enumerate(derived_outline(document), 1)}
    actual = {r["chapter_key"]: (r["ordinal"], r.get("chapter_label")) for r in stored}
    out = []
    for key in sorted(set(expected) | set(actual),
                      key=lambda k: (expected.get(k, actual.get(k))[0], k)):
        e, a = expected.get(key), actual.get(key)
        if a is None:
            out.append(f"{key}: not stored (expected ordinal {e[0]})")
        elif e is None:
            out.append(f"{key}: stored at ordinal {a[0]}, no passage holds it")
        elif e[0] != a[0]:
            out.append(f"{key}: ordinal {a[0]}, expected {e[0]}")
        elif e[1] != a[1]:
            out.append(f"{key}: label differs at ordinal {a[0]}")
    return out


def read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def outline_failures(snapshot_dir: str, live: dict[str, list[Document]]) -> list[Failure] | None:
    """Failures for every judged document of the collections in `live`, or None when
    the snapshot has no document_chapters.jsonl."""
    path = os.path.join(snapshot_dir, CHAPTERS_FILE)
    if not os.path.exists(path):
        return None
    stored: dict[str, list[dict]] = {}
    for row in read_rows(path):
        stored.setdefault(row["document_id"], []).append(row)
    counts = {d["id"]: d.get("chunk_count")
              for d in read_rows(os.path.join(snapshot_dir, DOCUMENTS_FILE))}
    failures = []
    for collection, documents in sorted(live.items()):
        for document in documents:
            if counts.get(document.id) is None:
                continue
            problems = compare(stored.get(document.id, []), document)
            if problems:
                more = len(problems) - DETAILS_LISTED
                failures.append(Failure(
                    check="outline_matches", collection=collection, document_id=document.id,
                    passage_id=document.id, anchor=None, score=None,
                    detail="; ".join(problems[:DETAILS_LISTED])
                           + (f"; and {more} more" if more > 0 else "")))
    return failures
