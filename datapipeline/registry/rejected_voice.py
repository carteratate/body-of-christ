"""Rejected-voice ranges (corpus-cleanup 3.4; Decision log "Rejected voices (C-01)").

`rejected_voice_ranges.json` lists, per range, the document, its first and last anchor in
reading order, the label pattern and the basis (the condemning act or the work's own
reply). No passage text. Every passage of a range carries `voice = "rejected"` and its
label as `unit_label`, through its passage-registry row (2.1's overrides, D11), which
`scripts/rejected_voice_rows.py` writes from a build. `check` is the build check
`roles.rejected_voice`.

A label pattern may hold `{n}`, the number that ends the passage's unit anchor
(`exsurge-domine/10` → 10), for lists whose passages are one numbered proposition each.

The Summa's objections carry the role from the adapter (1.7) and are not listed here.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from identity import unit_anchor
from model import Document, Passage

REGISTRY_DIR = os.path.dirname(os.path.abspath(__file__))
RANGES_FILE = os.path.join(REGISTRY_DIR, "rejected_voice_ranges.json")
VOICE = "rejected"
FIELDS = ("collection", "document_id", "title", "first_anchor", "last_anchor", "label",
          "basis")
_NUMBER = re.compile(r"(\d+)$")
_PLACEHOLDER = re.compile(r"\{(\w*)\}")


@dataclass(frozen=True)
class Range:
    collection: str
    document_id: str
    title: str
    first_anchor: str
    last_anchor: str
    label: str
    basis: str

    def label_for(self, passage: Passage) -> str:
        if "{n}" not in self.label:
            return self.label
        m = _NUMBER.search(unit_anchor(passage.anchor))
        if m is None:
            raise ValueError(f"{self.title} {passage.anchor}: no number for {self.label!r}")
        return self.label.replace("{n}", m[1])


def load_ranges(path: str = RANGES_FILE) -> list[Range]:
    with open(path, encoding="utf-8") as f:
        return [Range(**{k: r[k] for k in FIELDS}) for r in json.load(f)]


def validate(ranges: list[Range], works: list[dict]) -> list[str]:
    """What the ranges file must hold without a build: every field, a registered
    document of the named collection, `{n}` as the only placeholder, sorted by collection
    and document (a document's ranges in reading order, which only a build can check)."""
    out = []
    collection_of = {w["document_id"]: w["collection"] for w in works}
    keys = [(r.collection, r.document_id) for r in ranges]
    if keys != sorted(keys):
        out.append("rejected_voice_ranges.json is not sorted by collection and document")
    for r in ranges:
        name = f"{r.title} {r.first_anchor}"
        for k in FIELDS:
            if not getattr(r, k):
                out.append(f"{name}: no {k}")
        if collection_of.get(r.document_id) != r.collection:
            out.append(f"{name}: document {r.document_id} is not in {r.collection}")
        if any(p != "n" for p in _PLACEHOLDER.findall(r.label)):
            out.append(f"{name}: label {r.label!r} holds a placeholder other than {{n}}")
    return out


def expand(document: Document, r: Range) -> list[Passage]:
    """The passages of `r`, in reading order; ValueError if either anchor is not in the
    build or the last comes before the first."""
    anchors = [p.anchor for p in document.passages]
    for a in (r.first_anchor, r.last_anchor):
        if a not in anchors:
            raise ValueError(f"{r.title}: anchor {a} is not in the build")
    i, j = anchors.index(r.first_anchor), anchors.index(r.last_anchor)
    if j < i:
        raise ValueError(f"{r.title}: {r.last_anchor} comes before {r.first_anchor}")
    return document.passages[i:j + 1]


def labels(documents: list[Document], ranges: list[Range]) -> dict[tuple[str, str], str]:
    """(document ID, anchor) → label for every passage in a range of these documents;
    ValueError if a range does not resolve or two ranges share a passage."""
    by_id = {d.id: d for d in documents}
    out: dict[tuple[str, str], str] = {}
    for r in ranges:
        d = by_id.get(r.document_id)
        if d is None:
            continue
        for p in expand(d, r):
            if (d.id, p.anchor) in out:
                raise ValueError(f"{r.title}: {p.anchor} is in two ranges")
            out[(d.id, p.anchor)] = r.label_for(p)
    return out


def summa_objection(collection: str, passage: Passage) -> bool:
    """A Summa objection, which 1.7's adapter marks rejected."""
    return collection == "summa" and (passage.unit_label or "").startswith("Objection")


def check(collection: str, documents: list[Document], ranges: list[Range]
          ) -> dict[str, list[str]]:
    """`roles.rejected_voice:<collection>`: every range of the collection resolves to
    anchors in the build; every passage in a range carries the role and its label; no
    other passage carries the role but a Summa objection. `documents` have the registry's
    overrides applied. Units: "<document ID>#<anchor>: <problem>"."""
    units = []
    mine = [r for r in ranges if r.collection == collection]
    built = {d.id for d in documents}
    for r in mine:
        if r.document_id not in built:
            units.append(f"{r.document_id}: {r.title} is not in the build")
    try:
        wanted = labels(documents, mine)
    except ValueError as e:
        units.append(str(e))
        wanted = {}
    for d in documents:
        for p in d.passages:
            label = wanted.get((d.id, p.anchor))
            if label is not None:
                if p.voice != VOICE:
                    units.append(f"{d.id}#{p.anchor}: no rejected voice")
                if p.unit_label != label:
                    units.append(f"{d.id}#{p.anchor}: label {p.unit_label!r}, not {label!r}")
            elif p.voice == VOICE and not summa_objection(collection, p):
                units.append(f"{d.id}#{p.anchor}: rejected voice outside every range")
    return {f"roles.rejected_voice:{collection}": units} if units else {}
