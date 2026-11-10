"""Each papal document's genre and form, read from the tracked `papal_genres.csv` (1.3b).

The genre is the document's kind, what it is; the form is how the papal chancery issued
it, `bull` or `brief`, empty where none is recorded (Carter, 9 Nov 2026). Each row cites
its evidence: the document's heading on vatican.va, or other evidence where the heading
names no genre. `scripts/vendor_sources.py` copies both values into the three papal
manifests, which are gitignored, so this table is what reviewers read.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from registry.genres import OTHER, PAPAL_FORMS, PAPAL_GENRES

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "papal_genres.csv")
COLLECTIONS = ("encyclicals", "apostolic-exhortations", "papal-documents")
GENRES = PAPAL_GENRES + (OTHER,)
COLUMNS = ["slug", "collection", "genre", "form", "evidence_url", "evidence"]


@dataclass(frozen=True)
class Labels:
    collection: str
    genre: str
    form: str | None
    evidence_url: str
    evidence: str


def problems(path: str = PATH) -> list[str]:
    """One message per malformed row; empty when the table is sound."""
    out: list[str] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            return [f"columns {reader.fieldnames} are not {COLUMNS}"]
        for row in reader:
            slug = row["slug"]
            if slug in seen:
                out.append(f"{slug}: listed twice")
            seen.add(slug)
            if row["collection"] not in COLLECTIONS:
                out.append(f"{slug}: collection {row['collection']!r}")
            if row["genre"] not in GENRES:
                out.append(f"{slug}: genre {row['genre']!r} is not in PAPAL_GENRES or other")
            if row["form"] and row["form"] not in PAPAL_FORMS:
                out.append(f"{slug}: form {row['form']!r} is not in PAPAL_FORMS")
            if not row["evidence_url"].startswith("https://") and \
                    not row["evidence_url"].startswith("http://"):
                out.append(f"{slug}: no evidence URL")
            if not row["evidence"].strip():
                out.append(f"{slug}: no evidence")
    return out


def load(path: str = PATH) -> dict[str, Labels]:
    """Labels by slug. Refuses a malformed table rather than vendor a bad value."""
    bad = problems(path)
    if bad:
        raise ValueError(f"{path}: " + "; ".join(bad))
    with open(path, encoding="utf-8", newline="") as f:
        return {r["slug"]: Labels(r["collection"], r["genre"], r["form"] or None,
                                  r["evidence_url"], r["evidence"])
                for r in csv.DictReader(f)}


# The genre each collection was named for. Papal documents holds the rest, so a document
# there disagrees only when it is one of these.
_COLLECTION_GENRE = {"encyclicals": "encyclical", "apostolic-exhortations": "apostolic-exhortation"}


def disagrees(collection: str, genre: str) -> bool:
    """Whether a genre contradicts the collection a document is filed in. 1.3b moves no
    document (IDs include the collection; 5.1b merges the collections)."""
    if collection in _COLLECTION_GENRE:
        return genre != _COLLECTION_GENRE[collection]
    return genre in _COLLECTION_GENRE.values()


def report(sources: str) -> str:
    """Counts per collection and genre, per form, and every document whose genre
    disagrees with its collection, read from the vendored manifests."""
    import json
    from collections import Counter

    by_genre: Counter = Counter()
    by_form: Counter = Counter()
    lines: list[str] = []
    for collection in COLLECTIONS:
        with open(os.path.join(sources, collection, "manifest.json"), encoding="utf-8") as f:
            for e in json.load(f):
                by_genre[(collection, e.get("genre"))] += 1
                by_form[e.get("form") or "none"] += 1
                if disagrees(collection, e.get("genre")):
                    form = f", issued as a {e['form']}" if e.get("form") else ""
                    lines.append(f"  {collection}/{e['slug']} ({e['title']}, {e['year']}): "
                                 f"{e.get('genre')}{form}")
    out = ["Per collection and genre:"]
    out += [f"  {c} / {g}: {n}" for (c, g), n in sorted(by_genre.items(), key=str)]
    out += ["Per form:"] + [f"  {k}: {n}" for k, n in sorted(by_form.items())]
    out += [f"Genre disagrees with collection ({len(lines)}):"] + lines
    return "\n".join(out)


if __name__ == "__main__":
    print(report(os.path.join(os.path.dirname(PATH), "sources")))
