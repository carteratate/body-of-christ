"""Passage health rules (corpus-cleanup item 0.1b).

Block rules (H1 to H5) describe passages that are never useful: blank text, page-number or
punctuation debris, broken positions and anchors. `refuse_block_violations` runs them in
`CollectionPublicationRunner._validate_documents`, before any store is acquired, and
refuses the publication. Report rules (R1 to R8) count softer problems per collection, so
P1 PRs can show them falling; they never block.

A block violation whose check id is in `checks/known_defects.json` does not refuse: it is
an accepted defect with a named fixing PR, and the strict xfail in
`tests/source_checks/test_health_sources.py` forces that PR to delete the entry, after
which the rule blocks it like any other. Only the listed passage is accepted, so a new one
of the same kind blocks at once.

The patterns and allowlists the report rules use are data, in `health_patterns.json`.
Nothing here reads `ingest/`: the rules see only the built Documents.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from model import Document

DATAPIPELINE = os.path.dirname(os.path.abspath(__file__))
PATTERNS_PATH = os.path.join(DATAPIPELINE, "health_patterns.json")
KNOWN_DEFECTS_PATH = os.path.join(DATAPIPELINE, "checks", "known_defects.json")

BLOCK_RULES = ("H1_blank", "H2_debris", "H3_positions", "H4_anchor_unique",
               "H5_anchor_nonempty")
REPORT_RULES = ("R1_short", "R2_footer", "R3_note_start", "R4_dup_text",
                "R5_repeated_reference", "R6_joined_paragraphs", "R7_non_english",
                "R8_anchor_suffix")
RULES = BLOCK_RULES + REPORT_RULES

# Stripped content made only of digits, Roman-numeral letters, spaces and punctuation: a
# page number, a section numeral or a stray mark. Blank content is H1's, not this rule's.
# A block rule, so it stays in code rather than in the patterns file.
DEBRIS = re.compile(r'^[0-9IVXLCivxlc .,;:()\[\]"“”\'’-]*$')
# R4 compares texts of at least this many characters, after normalization.
DUP_MIN_CHARS = 100
# How many violations a refusal lists.
REFUSAL_LISTED = 10

Severity = Literal["block", "report"]


@dataclass(frozen=True)
class Violation:
    rule: str
    severity: Severity
    collection: str
    document_id: str
    anchor: str | None
    detail: str

    @property
    def check_id(self) -> str:
        """Stable id, one per passage (or per document for H3), the form
        known_defects.json uses: health.<rule>:<collection>/<document_id>[#<anchor>]."""
        where = f"{self.collection}/{self.document_id}"
        anchor = "" if self.anchor is None else f"#{self.anchor}"
        return f"health.{self.rule}:{where}{anchor}"


@lru_cache(maxsize=None)
def load_patterns(path: str = PATTERNS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _for_collection(rule: dict, collection: str) -> list[str]:
    return list(rule.get("all", [])) + list(rule.get(collection, []))


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


# --------------------------------------------------------------------------- block rules

def _block(collection: str, document: Document) -> list[Violation]:
    out: list[Violation] = []

    def add(rule: str, anchor: str | None, detail: str) -> None:
        out.append(Violation(rule, "block", collection, document.id, anchor, detail))

    positions = [p.position for p in document.passages]
    if positions != list(range(len(positions))):
        first = next(i for i, pos in enumerate(positions) if pos != i)
        add("H3_positions", None,
            f"{len(positions)} passages; index {first} holds position {positions[first]}")

    anchors = Counter(p.anchor for p in document.passages)
    reported: set[str] = set()
    for p in document.passages:
        text = p.content.strip()
        if not text:
            add("H1_blank", p.anchor, "content is empty after strip()")
        elif DEBRIS.match(text):
            add("H2_debris", p.anchor, f"{len(text)} character{'s' * (len(text) != 1)} of digits, "
                "numerals or punctuation")
        if anchors[p.anchor] > 1 and p.anchor not in reported:
            reported.add(p.anchor)
            add("H4_anchor_unique", p.anchor, f"anchor used by {anchors[p.anchor]} passages")
        empty = [name for name in ("anchor", "chapter_key", "chapter_label")
                 if not (getattr(p, name) or "").strip()]
        if empty:
            add("H5_anchor_nonempty", p.anchor,
                f"empty {', '.join(empty)} at position {p.position}")
    return out


# --------------------------------------------------------------------------- report rules

def _report(collection: str, document: Document, patterns: dict) -> list[Violation]:
    out: list[Violation] = []

    def add(rule: str, anchor: str, detail: str) -> None:
        out.append(Violation(rule, "report", collection, document.id, anchor, detail))

    short = patterns["R1_short"]
    short_allowed = collection in short["allowed_collections"]
    footers = [re.compile(p) for p in _for_collection(patterns["R2_footer"], collection)]
    notes_rule = patterns["R3_note_start"]
    notes = ([] if collection in notes_rule.get("skip_collections", [])
             else [re.compile(p) for p in _for_collection(notes_rule, collection)])
    abbreviations = set(patterns["R6_joined_paragraphs"]["abbreviations"])
    lang = patterns["R7_non_english"]
    function_words = set(lang["function_words"])

    references = Counter(p.reference for p in document.passages)
    texts: dict[str, list[str]] = defaultdict(list)

    for p in document.passages:
        text = p.content.strip()
        if not short_allowed and 0 < len(text) < short["max_chars"] \
                and re.search(r"[^\W\d_]", text):
            add("R1_short", p.anchor, f"{len(text)} character{'s' * (len(text) != 1)}")

        markers = [m.pattern for m in footers if m.search(p.content)]
        if markers:
            add("R2_footer", p.anchor, f"matches {', '.join(markers)}")

        note = next((m.pattern for m in notes if m.match(text)), None)
        if note:
            add("R3_note_start", p.anchor, f"starts like a note ({note})")

        normalized = _normalize(text)
        if len(normalized) >= DUP_MIN_CHARS:
            texts[normalized].append(p.anchor)

        if references[p.reference] > 1:
            add("R5_repeated_reference", p.anchor,
                f"reference shared by {references[p.reference]} passages")

        joins = [m for m in re.finditer(r"([^\W\d_]*[a-z])[.!?][A-Z]", p.content)
                 if len(m.group(1)) > 1 and m.group(1).lower() not in abbreviations]
        if joins:
            add("R6_joined_paragraphs", p.anchor,
                f"{len(joins)} join{'s' * (len(joins) != 1)}")

        # One report per passage: a note is R3's, not a language problem.
        if note is None and len(text) >= lang["min_chars"]:
            words = re.findall(r"[^\W\d_]+", text.lower())
            numbers = re.findall(r"\d+", text)
            if words and len(numbers) / (len(words) + len(numbers)) < lang["max_digit_share"]:
                share = sum(w in function_words for w in words) / len(words)
                if share < lang["max_share"]:
                    add("R7_non_english", p.anchor, f"function-word share {share:.3f}")

        if "--" in p.anchor:
            add("R8_anchor_suffix", p.anchor, "label-derived disambiguation suffix")

    for anchors in texts.values():
        for anchor in anchors[1:]:
            add("R4_dup_text", anchor, f"same text as {anchors[0]}")
    return out


# --------------------------------------------------------------------------- entry points

def check_documents(collection: str, documents: list[Document], *,
                    report: bool = True) -> list[Violation]:
    """Every violation of the block rules, and of the report rules unless `report` is
    False (the publish gate needs only the block rules)."""
    patterns = load_patterns() if report else {}
    out: list[Violation] = []
    for document in documents:
        out += _block(collection, document)
        if report:
            out += _report(collection, document, patterns)
    order = {rule: i for i, rule in enumerate(RULES)}
    return sorted(out, key=lambda v: order[v.rule]) if report else out


def known_block_defects(path: str = KNOWN_DEFECTS_PATH) -> set[str]:
    """Check ids of block violations accepted as known defects."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {k for k in json.load(f) if k.startswith("health.")}


def refuse_block_violations(collection: str, documents: list[Document],
                            known: set[str] | None = None) -> None:
    """Raise ValueError("REFUSING: ...") if any block rule fires on a passage that is not
    a known defect, listing the first REFUSAL_LISTED violations."""
    known = known_block_defects() if known is None else known
    blocking = [v for v in check_documents(collection, documents, report=False)
                if v.check_id not in known]
    if not blocking:
        return
    listed = "; ".join(f"{v.rule} {v.document_id}#{v.anchor or '-'} ({v.detail})"
                       for v in blocking[:REFUSAL_LISTED])
    more = len(blocking) - REFUSAL_LISTED
    raise ValueError(
        f"REFUSING: {len(blocking)} health block-rule violations in '{collection}': {listed}"
        + (f"; and {more} more" if more > 0 else "")
    )
