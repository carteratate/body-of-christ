"""Passage health rules (corpus-cleanup item 0.1b).

Block rules (H1 to H5, R10, and R9 in the papal collections) describe passages that are
never useful: blank text, page-number or punctuation debris, broken positions and anchors,
a website's own text, a heading stranded at the end of a passage. H6 to H8 hold the
headings marked in `metadata.headings` (issue #445, `headings.py`): H6 refuses a malformed
mark wherever one is written, and H7 (a heading-like paragraph left unmarked) and H8 (a
level-1 heading that repeats its chapter label without `chapter_title`) apply only to the
collections listed under `H7_unmarked_heading` in `health_patterns.json`, which a
collection joins when its adapter marks its headings, and to the documents listed there
(a new work whose collection's other documents are not marked yet). `refuse_block_violations` runs them in
`CollectionPublicationRunner._validate_documents`, before any store is acquired, and
refuses the publication. Report rules (R1 to R8, R11 to R14 and the named rules after them)
count softer problems per collection, so P1 PRs can show them falling; they never block.
0.1d added R9 to R14, `no_ligatures` and `summa_bracket_numbers` for the 6 Oct 2026 corpus
reviews.

A block violation whose check id is in `checks/known_defects.json` does not refuse: it is
an accepted defect with a named fixing PR, and the strict xfail in
`tests/source_checks/test_health_sources.py` forces that PR to delete the entry, after
which the rule blocks it like any other. Only the listed passage is accepted, so a new one
of the same kind blocks at once.

The report rules in TRACKED_REPORT_RULES have an owning item too. Each is tracked as one
known defect per document (`health.<rule>:<collection>/<document_id>`, see
`tracked_check_ids`) that lists the anchors it fires on, so the fixing PR sees it clear and
a new passage shows as growth; it never blocks.

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

import headings
from model import Document, Passage

DATAPIPELINE = os.path.dirname(os.path.abspath(__file__))
PATTERNS_PATH = os.path.join(DATAPIPELINE, "health_patterns.json")
KNOWN_DEFECTS_PATH = os.path.join(DATAPIPELINE, "checks", "known_defects.json")

BLOCK_RULES = ("H1_blank", "H2_debris", "H3_positions", "H4_anchor_unique",
               "H5_anchor_nonempty", "R10_site_boilerplate", "R9_trailing_heading",
               "H6_heading_marks", "H7_unmarked_heading", "H8_chapter_title")
REPORT_RULES = ("R1_short", "R2_footer", "R3_note_start", "R4_dup_text",
                "R5_repeated_reference", "R6_joined_paragraphs", "R7_non_english",
                "R8_anchor_suffix", "R11_papal_editorial",
                "R12_note_caller", "R13_lower_start", "R14_hyphen_space", "no_ligatures",
                "summa_bracket_numbers")
# Report rules whose hits an item has promised to clear (REVIEW-GAPS-PLAN section 6). Each
# is one known defect per collection that lists its passages; the other report rules are
# counted only.
TRACKED_REPORT_RULES = ("R11_papal_editorial", "R12_note_caller",
                        "no_ligatures", "summa_bracket_numbers")
RULES = BLOCK_RULES + REPORT_RULES

# Stripped content made only of digits, Roman-numeral letters, spaces and punctuation: a
# page number, a section numeral or a stray mark. Blank content is H1's, not this rule's.
# A block rule, so it stays in code rather than in the patterns file.
DEBRIS = re.compile(r'^[0-9IVXLCivxlc .,;:()\[\]"“”\'’-]*$')
# no_ligatures: the letters æ, œ, Æ and Œ, which keyword search cannot match to "ae", "oe".
LIGATURES = re.compile("[æœÆŒ]")
# summa_bracket_numbers: a bracketed number left by the source's cross-reference links.
SUMMA_BRACKET = re.compile(r"\[\d+\]")
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
    # Set only when the anchor is empty or shared, so the check id still names one passage.
    position: int | None = None

    @property
    def check_id(self) -> str:
        """Stable id, one per passage (or per document for H3), the form
        known_defects.json uses: health.<rule>:<collection>/<document_id>[#<anchor>], with
        @<position> added when the anchor is empty or shared."""
        where = f"{self.collection}/{self.document_id}"
        anchor = "" if self.anchor is None else f"#{self.anchor}"
        position = "" if self.position is None else f"@{self.position}"
        return f"health.{self.rule}:{where}{anchor}{position}"


@lru_cache(maxsize=None)
def load_patterns(path: str = PATTERNS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _for_collection(rule: dict, collection: str) -> list[str]:
    return list(rule.get("all", [])) + list(rule.get(collection, []))


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


def _violation(rule: str, severity: Severity, collection: str, document: Document,
               passage: Passage | None, anchors: Counter, detail: str) -> Violation:
    if passage is None:
        return Violation(rule, severity, collection, document.id, None, detail)
    shared = not passage.anchor.strip() or anchors[passage.anchor] > 1
    return Violation(rule, severity, collection, document.id, passage.anchor, detail,
                     passage.position if shared else None)


# --------------------------------------------------------------------------- block rules

def _block(collection: str, document: Document) -> list[Violation]:
    out: list[Violation] = []
    patterns = load_patterns()
    boilerplate = patterns["R10_site_boilerplate"]["all"]
    heading = patterns["R9_trailing_heading"]
    heading_end = re.compile(heading["final_punctuation"])

    anchors = Counter(p.anchor for p in document.passages)

    def add(rule: str, passage: Passage | None, detail: str) -> None:
        out.append(_violation(rule, "block", collection, document, passage, anchors, detail))

    positions = [p.position for p in document.passages]
    if positions != list(range(len(positions))):
        first = next(i for i, pos in enumerate(positions) if pos != i)
        add("H3_positions", None,
            f"{len(positions)} passages; index {first} holds position {positions[first]}")

    reported: set[str] = set()
    for i, p in enumerate(document.passages):
        text = p.content.strip()
        if not text:
            add("H1_blank", p, "content is empty after strip()")
        elif DEBRIS.match(text):
            add("H2_debris", p, f"{len(text)} character{'s' * (len(text) != 1)} of digits, "
                "numerals or punctuation")
        if anchors[p.anchor] > 1 and p.anchor not in reported:
            reported.add(p.anchor)
            add("H4_anchor_unique", p, f"anchor used by {anchors[p.anchor]} passages")
        empty = [name for name in ("anchor", "chapter_key", "chapter_label")
                 if not (getattr(p, name) or "").strip()]
        if empty:
            add("H5_anchor_nonempty", p,
                f"empty {', '.join(empty)} at position {p.position}")
        lowered = p.content.lower()
        found = [s for s in boilerplate if s.lower() in lowered]
        if found:
            add("R10_site_boilerplate", p, f"contains {', '.join(found)}")
        if collection in heading["collections"] and i + 1 < len(document.passages):
            lines = [line.strip() for line in p.content.split("\n") if line.strip()]
            last = lines[-1] if lines else ""
            if len(lines) > 1 and len(last) < heading["max_chars"] \
                    and last[:1].isupper() and not heading_end.search(last):
                add("R9_trailing_heading", p, f"ends with a {len(last)}-character line")
    out += _heading_rules(collection, document, add)
    return out


def _heading_rules(collection: str, document: Document, add) -> list[Violation]:
    """H6 on every passage that carries marks; H7 and H8 in the collections that opt in.
    Calls `add` and returns [] so it reads like the rules above."""
    rule = load_patterns()["H7_unmarked_heading"]
    # A whole collection, its documents by one author (Vatican II among the councils), or
    # one document at a time (a new work in a collection whose others are not marked; 5.6a, 5.6b).
    opted_in = (collection in rule["collections"]
                or document.id in rule.get("documents", [])
                or document.author in rule.get("authors", {}).get(collection, ()))
    not_headings = {headings.normalized(entry["text"])
                    for entry in rule["not_headings"].get(document.id, [])}
    seen_chapters: set[str] = set()
    for p in document.passages:
        marks = (p.metadata or {}).get(headings.KEY)
        found = headings.problems(p.content, marks)
        if found:
            add("H6_heading_marks", p, "; ".join(found[:3]))
        opens_chapter = p.chapter_key not in seen_chapters
        seen_chapters.add(p.chapter_key)
        if not opted_in or found:
            continue
        marks = marks or []
        covered = {(m["at"], m["end"]) for m in marks}
        paras = headings.paragraphs(p.content)
        # A passage of one paragraph is its own text unless that names a division (a
        # piece that held only its title).
        looks = headings.looks_like_heading if len(paras) > 1 else headings.looks_like_division
        unmarked = [p.content[a:b] for a, b in paras if (a, b) not in covered
                    and looks(p.content[a:b])
                    and headings.normalized(p.content[a:b]) not in not_headings]
        if unmarked:
            add("H7_unmarked_heading", p, f"{len(unmarked)} unmarked heading-like "
                f"paragraph{'s' * (len(unmarked) != 1)}, first {unmarked[0][:60]!r}")
        if opens_chapter:
            for group, words in headings.opening_titles(p.content, marks):
                if not any(marks[i].get("chapter_title") for i in group) \
                        and headings.repeats_label(words, p.chapter_label or ""):
                    add("H8_chapter_title", p, f"opening level-1 heading {words[:60]!r} "
                        "repeats the chapter label without chapter_title")
    return []


# --------------------------------------------------------------------------- report rules

def _report(collection: str, document: Document, patterns: dict) -> list[Violation]:
    out: list[Violation] = []

    anchors = Counter(p.anchor for p in document.passages)

    def add(rule: str, passage: Passage, detail: str) -> None:
        out.append(_violation(rule, "report", collection, document, passage, anchors, detail))

    short = patterns["R1_short"]
    short_allowed = collection in short["allowed_collections"]
    footers = [re.compile(p) for p in _for_collection(patterns["R2_footer"], collection)]
    notes_rule = patterns["R3_note_start"]
    notes = ([] if collection in notes_rule.get("skip_collections", [])
             else [re.compile(p) for p in _for_collection(notes_rule, collection)])
    abbreviations = set(patterns["R6_joined_paragraphs"]["abbreviations"])
    lang = patterns["R7_non_english"]
    function_words = set(lang["function_words"])

    editorial = ([re.compile(x) for x in patterns["R11_papal_editorial"]["patterns"]]
                 if collection in patterns["R11_papal_editorial"]["collections"] else [])
    callers_rule = patterns["R12_note_caller"]
    caller_patterns = ([] if collection in callers_rule["skip_collections"]
                       else [re.compile(x) for x in callers_rule["patterns"]])
    caller_skip = [re.compile(x) for x in callers_rule["not_after"]]
    hyphen_rule = patterns["R14_hyphen_space"]
    hyphen = re.compile(hyphen_rule["pattern"])
    hyphen_allowed = set(hyphen_rule["allowed"])

    references = Counter(p.reference for p in document.passages)
    texts: dict[str, list[Passage]] = defaultdict(list)

    for i, p in enumerate(document.passages):
        text = p.content.strip()
        if not short_allowed and 0 < len(text) < short["max_chars"] \
                and re.search(r"[^\W\d_]", text):
            add("R1_short", p, f"{len(text)} character{'s' * (len(text) != 1)}")

        markers = [m.pattern for m in footers if m.search(p.content)]
        if markers:
            add("R2_footer", p, f"matches {', '.join(markers)}")

        note = next((m.pattern for m in notes if m.match(text)), None)
        if note:
            add("R3_note_start", p, f"starts like a note ({note})")

        normalized = _normalize(text)
        if len(normalized) >= DUP_MIN_CHARS:
            texts[normalized].append(p)

        if references[p.reference] > 1:
            add("R5_repeated_reference", p,
                f"reference shared by {references[p.reference]} passages")

        joins = [m for m in re.finditer(r"([^\W\d_]*[a-z])[.!?][A-Z]", p.content)
                 if len(m.group(1)) > 1 and m.group(1).lower() not in abbreviations]
        if joins:
            add("R6_joined_paragraphs", p,
                f"{len(joins)} join{'s' * (len(joins) != 1)}")

        # One report per passage: a note is R3's, not a language problem.
        if note is None and len(text) >= lang["min_chars"]:
            words = re.findall(r"[^\W\d_]+", text.lower())
            numbers = re.findall(r"\d+", text)
            if words and len(numbers) / (len(words) + len(numbers)) < lang["max_digit_share"]:
                share = sum(w in function_words for w in words) / len(words)
                if share < lang["max_share"]:
                    add("R7_non_english", p, f"function-word share {share:.3f}")

        if "--" in p.anchor:
            add("R8_anchor_suffix", p, "label-derived disambiguation suffix")

        found = [m.pattern for m in editorial if m.search(p.content)]
        if found:
            add("R11_papal_editorial", p, f"matches {', '.join(found)}")

        callers = _note_callers(p.content, caller_patterns, caller_skip)
        if callers:
            add("R12_note_caller", p, f"{callers} caller{'s' * (callers != 1)}")

        if text[:1].islower():
            add("R13_lower_start", p, "starts with a lowercase letter")

        broken = [m.group(0) for m in hyphen.finditer(p.content)
                  if m.group(0).lower() not in hyphen_allowed]
        if broken:
            add("R14_hyphen_space", p, f"{len(broken)} hyphen-space join"
                f"{'s' * (len(broken) != 1)}")

        ligatures = LIGATURES.findall(p.content)
        if ligatures:
            add("no_ligatures", p, f"{len(ligatures)} ligature{'s' * (len(ligatures) != 1)}")

        if collection == "summa":
            brackets = SUMMA_BRACKET.findall(p.content)
            if brackets:
                add("summa_bracket_numbers", p, f"{len(brackets)} bracketed number"
                    f"{'s' * (len(brackets) != 1)}")

    for same in texts.values():
        for p in same[1:]:
            add("R4_dup_text", p, f"same text as {same[0].anchor}")

    labels = [name for name in ("title", "author") if LIGATURES.search(getattr(document, name) or "")]
    if labels:
        out.append(Violation("no_ligatures", "report", collection, document.id, None,
                             f"ligature in the document {' and '.join(labels)}"))
    return out


def _note_callers(text: str, patterns: list[re.Pattern], skip: list[re.Pattern]) -> int:
    """How many footnote callers `text` holds: matches of `patterns` whose preceding text
    does not end like a citation (`skip`, matched against the 16 characters before the
    caller's punctuation, as "Rom. i." before " 17")."""
    n = 0
    for pattern in patterns:
        for m in pattern.finditer(text):
            before = text[max(0, m.start() - 16):m.start() + 1]
            if not any(s.search(before) for s in skip):
                n += 1
    return n


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


def tracked_check_ids(violations: list[Violation]) -> dict[str, list[str]]:
    """The TRACKED_REPORT_RULES violations grouped into check ids, one per rule and
    document, `health.<rule>:<collection>/<document_id>` → the anchors it fires on (with
    @<position> where the anchor is empty or shared, and "(document)" for a document-level
    hit)."""
    out: dict[str, list[str]] = defaultdict(list)
    for v in violations:
        if v.rule in TRACKED_REPORT_RULES:
            unit = "(document)" if v.anchor is None else v.anchor
            if v.position is not None:
                unit += f"@{v.position}"
            out[f"health.{v.rule}:{v.collection}/{v.document_id}"].append(unit)
    return dict(out)


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
    # The check id is what a known_defects.json entry for the passage would be keyed by.
    listed = "; ".join(f"{v.check_id} ({v.detail})" for v in blocking[:REFUSAL_LISTED])
    more = len(blocking) - REFUSAL_LISTED
    raise ValueError(
        f"REFUSING: {len(blocking)} health block-rule violations in '{collection}': {listed}"
        + (f"; and {more} more" if more > 0 else "")
    )
