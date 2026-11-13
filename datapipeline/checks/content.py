"""Role, editorial, attribution, label and text checks for the 6 Oct 2026 corpus reviews
(corpus-cleanup item 0.1d).

Each check reads the built Documents (one reads the work registry) and returns its
failures as check ids → the units behind each, the form `checks.report` and
`checks/known_defects.json` use. Every id is `<namespace>.<check>:<collection>[/<scope>]`,
so `checks.report.check_scope` reads its collection from the id. The finding each check
measures is in docs/corpus-cleanup/REVIEW-GAPS-PLAN.md, section 6.

Summa (units are anchors, or paragraph ids where a paragraph has no passage of its own):
- `roles.summa.objection-after-replies:summa`: an "Objection" part after the article's
  determination, in an article that does not restart at "Objection 1" (C-04, Sol A-013).
- `roles.summa.variant-sed-contra-boundaries:summa`: every paragraph R7's corrections file
  gives the sed-contra role opens a passage labelled "On the contrary", rather than being
  folded into an objection (C-04, Sol follow-up B-001). Units: source paragraph ids.
- `text.summa.adjacent-duplicate-parts:summa`: no two adjacent parts of one article have
  the same text (C-14, Sol A-012).
- `roles.summa.unbold-paragraph-openings:summa`: no part holds, at the start of one of its
  later paragraphs, a canonical opening ("On the contrary", "I answer that", "The
  contrary, however", "Reply OBJ") that should have opened a part of its own (C-14, Sol
  A-016, B-001). Units: anchors.
- `attribution.summa.editor-supplied-replies:summa`: every paragraph R7's corrections file
  flags as editorial or editor-supplied is excluded from the build, recorded in the
  document's `excluded_paragraphs`, and anchors no passage (C-04, Sol A-019). Units:
  source paragraph ids.
- `context.summa.reply-targets:summa`: every argument a passage answers
  (`metadata["reply_targets"]`) is in its article: an objection numbered so, or a sed
  contra with that number; or a unit the corrections file records as missing, in an
  article whose first passage carries the reader note (C-14, Sol A-017; Decision log
  "Summa reply targets (1.7)"). Units: "<anchor>:<target>".
- `labels.summa_reference_has_question:summa`: every article passage's reference ends
  with ": " and the article's question, the same for the whole article (Decision log
  "Summa citation form (1.7)"). Units: anchors.

Church Fathers and medieval (`:<collection>/<document_id>`, units are anchors):
- `editorial.argument_lines`: no paragraph is an editor's "Argument" summary (C-12),
  except R4's Refutation summaries, which are the author's.
- `editorial.chapter_title_lines`: no passage of the works in CHAPTER_TITLE_WORKS opens
  with a later editor's "Chapter N.—Title" line (G-1; Decision log "Editors' chapter
  titles in passage text").
- `editorial.provenance_lines`: no unbracketed paragraph is an editor's source line
  ("Mai, Script. vet. collectio nova, vol. ix. p. 645") (C-22, Opus A-014).
- `attribution.letter_sender`: in a letter collection, the sender a letter's title line
  or greeting names is the letter's resolved author (C-02, Opus-2 B-001). Units: the
  letters' chapter keys.
- `labels.reference_author_consistent`: a passage's reference names no author but its
  resolved display author (C-15, Opus-2 B-003).
- `labels.unique_reference`: no two passages of a document share a reference (1.10c).
  Split pieces cite their own text, so a shared reference is two units cited alike: two
  chapters with one label, or a paragraph number the adapter reads twice. Not run on the
  Catechism until 1.6 adopts the piece citations. Units: the shared references.
- `labels.roman_case`: no Roman numeral title-cased ("Ii", "Vi") in a chapter or unit label
  (C-22, Opus A-022). Run on every collection.

Registry and collection:
- `attribution.narrative_of_author_death:<collection>/<document_id>`: no work registry
  row titled "Martyrdom…", "Passion…" or "Acts of…" credits the martyr it names without a
  note (C-15, Opus A-008).
- `registry.unique_title_per_collection:<collection>`: no two documents of a collection
  share a title once case, punctuation and ligatures are set aside (C-15, Opus A-016).
  Units: the shared normalized titles.
- `text.canon_law.ligature_corruption:canon-law`: no lowercase word holds a capital V or Y
  standing for a lost "ff" or "ffi" ligature (C-16, Sol A-005). Units: canon numbers.
"""
from __future__ import annotations

import itertools
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

from checks.structure import (article_id, load_summa_corrections, summa_articles_built,
                              summa_role)
from identity import unit_anchor
from ingest.pieces import unit_reference
from model import Document

CHECKS_DIR = os.path.dirname(os.path.abspath(__file__))
DATAPIPELINE = os.path.dirname(CHECKS_DIR)
WORKS_PATH = os.path.join(DATAPIPELINE, "registry", "works.json")

THML_COLLECTIONS = ("church-fathers", "medieval")

Failures = dict[str, list[str]]


def _paragraphs(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


def _fold(text: str) -> str:
    """For comparing names and titles: NFKC, ligatures spelled out, lowercase, letters and
    digits only, single spaces."""
    text = unicodedata.normalize("NFKC", text)
    for a, b in (("æ", "ae"), ("Æ", "Ae"), ("œ", "oe"), ("Œ", "Oe")):
        text = text.replace(a, b)
    return " ".join(re.sub(r"[\W_]+", " ", text.lower()).split())


# --------------------------------------------------------------------------- Summa

def summa_objection_after_replies(documents: list[Document]) -> Failures:
    anchors = []
    for d in documents:
        for _, group in itertools.groupby(d.passages, key=lambda p: p.chapter_key):
            passages = list(group)
            roles = [summa_role(p.unit_label) for p in passages]
            if "determination" not in roles:
                continue
            after = passages[roles.index("determination"):]
            if any(p.unit_label == "Objection 1" for p in after):
                continue        # a second article in one div: one-disputation-per-article
            anchors += [p.anchor for p in after if summa_role(p.unit_label) == "objection"]
    return {"roles.summa.objection-after-replies:summa": anchors} if anchors else {}


def summa_sed_contra_boundaries(documents: list[Document], corrections: dict) -> Failures:
    """The paragraphs R7 found are sed contras (`role: sed-contra` in its corrections
    file): unbolded or comma-less openings, and the four "The contrary, however"
    paragraphs. The translators' "Objection N: On the contrary" paragraphs carry only a
    `latin_role` there and keep their printed label (R7 question 1), so they are not
    checked."""
    by_anchor = {p.anchor: p for d in documents for p in d.passages}
    failing = []
    for paragraph, facts in sorted(corrections.get("paragraphs", {}).items()):
        if facts.get("role") != "sed-contra":
            continue
        div, _, para = paragraph.rpartition("-")
        p = by_anchor.get(f"summa/{div}/{para}")
        if p is None or summa_role(p.unit_label) != "sed-contra":
            failing.append(paragraph)
    return ({"roles.summa.variant-sed-contra-boundaries:summa": failing} if failing else {})


def _same_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


def summa_adjacent_duplicates(documents: list[Document]) -> Failures:
    anchors = []
    for d in documents:
        for a, b in zip(d.passages, d.passages[1:]):
            if (a.chapter_key == b.chapter_key and a.content.strip()
                    and _same_text(a.content) == _same_text(b.content)):
                anchors.append(b.anchor)
    return {"text.summa.adjacent-duplicate-parts:summa": anchors} if anchors else {}


_UNBOLD_OPENING = re.compile(r"\n\n(?:On the contrary\b|I answer that\b|The contrary, however|"
                            r"(?:Reply|Replies) OBJ\b)")


def summa_unbold_openings(documents: list[Document]) -> Failures:
    anchors = [p.anchor for d in documents for p in d.passages
               if _UNBOLD_OPENING.search(p.content)]
    return {"roles.summa.unbold-paragraph-openings:summa": anchors} if anchors else {}


def summa_editor_supplied(documents: list[Document], corrections: dict) -> Failures:
    flagged = [pid for pid, f in corrections.get("paragraphs", {}).items()
               if f.get("flag") in ("editorial", "editor-supplied")]
    failing = []
    for d in documents:
        excluded = {e["paragraph"] for e in (d.metadata or {}).get("excluded_paragraphs", [])}
        built = {unit_anchor(p.anchor) for p in d.passages}
        for pid in flagged:
            div, _, para = pid.rpartition("-")
            if pid not in excluded or f"summa/{div}/{para}" in built:
                failing.append(pid)
    return ({"attribution.summa.editor-supplied-replies:summa": sorted(set(failing))}
            if failing else {})


_SED_CONTRA_CITED = re.compile(r", sed contra(?: (\d+))?:")
_AD_CITED = re.compile(r", ad ([\d ,and]+):")


def summa_reply_targets(documents: list[Document], corrections: dict) -> Failures:
    articles = corrections.get("articles", {})
    held: dict[str, set[int]] = defaultdict(set)
    for pid, f in corrections.get("paragraphs", {}).items():
        article = f.get("move_to") or pid.rpartition("-")[0]
        held[article] |= {int(t.split()[1]) for t in f.get("holds", []) if t.startswith("sc ")}
    failing = []
    for article, passages in sorted(summa_articles_built(documents).items()):
        objections = {int(p.unit_label.split()[-1]) for p in passages
                      if summa_role(p.unit_label) == "objection"}
        # A sed contra's further arguments are its later paragraphs ("Further, …").
        sed_contras = set(held[article])
        paragraphs = 1 + sum(p.content.count("\n\n") for p in passages
                             if summa_role(p.unit_label) == "sed-contra")
        if any(summa_role(p.unit_label) == "sed-contra" for p in passages):
            sed_contras |= set(range(1, paragraphs + 1))
        for p in passages:
            m = _SED_CONTRA_CITED.search(p.reference)
            if m:
                sed_contras.add(int(m.group(1) or 1))
        noted = bool(passages[0].note)
        missing = {m["unit"] for m in articles.get(article, {}).get("missing", [])}
        for p in passages:
            # The translators print an answered sed contra as an objection ("Objection 4:
            # On the other hand"); the reply's Latin number ("ad 4") then names it.
            cited = {int(n) for n in re.findall(r"\d+", _AD_CITED.search(p.reference)[1])} \
                if _AD_CITED.search(p.reference) else set()
            for target in (p.metadata or {}).get("reply_targets", []):
                kind, n = target.split()
                found = int(n) in (objections if kind == "obj" else sed_contras) or (
                    kind == "sc" and cited and cited <= objections)
                if not found and not (target in missing and noted):
                    failing.append(f"{unit_anchor(p.anchor)}:{target}")
    failing = list(dict.fromkeys(failing))
    return {"context.summa.reply-targets:summa": failing} if failing else {}


def summa_reference_has_question(documents: list[Document]) -> Failures:
    failing = []
    for article, passages in summa_articles_built(documents).items():
        questions = {unit_reference(p.reference).partition(": ")[2] for p in passages}
        if len(questions) != 1 or not next(iter(questions)).strip():
            failing += [p.anchor for p in passages]
    return ({"labels.summa_reference_has_question:summa": sorted(failing)}
            if failing else {})


# --------------------------------------------------------------------------- editorial

ARGUMENT_LINE = re.compile(r"^(Chapter [IVXLC]+\.?\s*[—-]*\s*)?Argument\s*[.:—]")
# R4 (docs/research/R4-refutation.md): the Refutation's book summaries are Hippolytus's own.
AUTHORIAL_ARGUMENTS = frozenset({"church-fathers/third-century-2.xml#iii.iii"})
CHAPTER_TITLE_LINE = re.compile(r"^(?:Chapter|Chap\.) [IVXLC\d]+\.?\s*[—–-]+\s*\S")
# The works whose chapter titles are a later editor's (Decision log "Editors' chapter
# titles in passage text", 9 Oct 2026), by source key: On the Trinity, the Enchiridion, On
# the Catechising of the Uninstructed, Faith and the Creed and On Christian Doctrine (NPNF,
# 1.8b, which split the treatise volume into its works); the Banquet, On the Apparel of
# Women and To His Wife (ANF, 1.8a). City of God's titles are the ancient capitula and stay.
CHAPTER_TITLE_WORKS = frozenset({
    "church-fathers/on-the-holy-trinity.xml#iv.i",
    "church-fathers/on-the-holy-trinity.xml#iv.ii",
    "church-fathers/on-the-holy-trinity.xml#iv.iii",
    "church-fathers/on-the-holy-trinity.xml#iv.iv",
    "church-fathers/city-of-god.xml#v",
    "church-fathers/third-century-3.xml#xi.iii",
    "church-fathers/third-century.xml#iii.iii",
    "church-fathers/third-century.xml#iii.v",
})
PROVENANCE_LINE = re.compile(
    r"(?<![\w\[])(?:Mai|Script\.\s?[Vv]et\.|Gallandi|Galland|Apud|Fabricius|Combefis|Pitra|"
    r"Bandini|Routh|Lambecius|Ex Leontio|Ex Leontii|Spicil\.)(?=\W).*?"
    r"\b(?:vol|tom|p|pp|lib|col|cap|t)\.\s*[\divxlc]+")
PROVENANCE_MAX_CHARS = 200
# An editor's sentence that cites an edition in passing ("Miller refers us to Fabricius")
# is a note, not a source line.
_PROVENANCE_PROSE = re.compile(r"\brefers?\b")


def _source_key(document: Document) -> str:
    return (document.metadata or {}).get("source_key", "")


def argument_lines(collection: str, documents: list[Document]) -> Failures:
    out: Failures = {}
    for d in documents:
        if _source_key(d) in AUTHORIAL_ARGUMENTS:
            continue
        anchors = [p.anchor for p in d.passages
                   if any(ARGUMENT_LINE.match(line) for line in _paragraphs(p.content))]
        if anchors:
            out[f"editorial.argument_lines:{collection}/{d.id}"] = anchors
    return out


def chapter_title_lines(collection: str, documents: list[Document]) -> Failures:
    out: Failures = {}
    for d in documents:
        if _source_key(d) not in CHAPTER_TITLE_WORKS:
            continue
        anchors = []
        for p in d.passages:
            first = next(iter(_paragraphs(p.content)), "")
            if CHAPTER_TITLE_LINE.match(first) and not ARGUMENT_LINE.match(first):
                anchors.append(p.anchor)
        if anchors:
            out[f"editorial.chapter_title_lines:{collection}/{d.id}"] = anchors
    return out


def provenance_lines(collection: str, documents: list[Document]) -> Failures:
    out: Failures = {}
    for d in documents:
        anchors = [p.anchor for p in d.passages
                   if any(len(line) < PROVENANCE_MAX_CHARS and not line.startswith("[")
                          and PROVENANCE_LINE.search(line) and not _PROVENANCE_PROSE.search(line)
                          for line in _paragraphs(p.content))]
        if anchors:
            out[f"editorial.provenance_lines:{collection}/{d.id}"] = anchors
    return out


# --------------------------------------------------------------------------- attribution

LETTER_COLLECTION = re.compile(r"^(?:The )?(?:Epistles|Letters)\b")
LETTER_CHAPTER = re.compile(r"^(?:Epistle|Letter) [IVXLC]+\b")
# The editor's number line that opens a letter ("Epistle XXX. Oxford ed.: Ep. xxx."); the
# line after it is the editor's title line.
LETTER_NUMBER_LINE = re.compile(r"^(?:Epistle|Letter) [IVXLC]+\.")
# The editor's title line names the letter's direction. "To X" and "From A to X" with A
# the author are the author's; otherwise the words before " to "/" Replies"/" Answer"
# name the sender.
_TITLE_SENDER = re.compile(
    r"^(?:From |The Reply (?:to the Same )?of |The Answer of |The Letter of )?"
    r"(?P<sender>.+?)(?:’s Answer| Replies| Answer| to |,? on |$)")


def resolved_author(document: Document, passage) -> str:
    """The author a card shows for a passage: its passage_author, else its work's
    author, else the document's."""
    if passage.passage_author:
        return passage.passage_author
    if passage.work_key:
        work = next((w for w in document.works if w.work_key == passage.work_key), None)
        if work and work.author:
            return work.author
    return document.author or ""


_source_roots: dict[str, object] = {}


def source_letter_lines(document: Document, chapter_key: str) -> list[str] | None:
    """The opening paragraphs of a letter's div as the source prints them, notes left
    out, or None when the source file is not at hand. Rule G takes the editor's number
    and title lines out of the passages (1.8a), so the sender is read here, where they
    still are, until 1.8c records it as the letter's author."""
    from checks.source_text import SOURCES, _read_thml
    from ingest.common import _block_text, direct_blocks

    meta = document.metadata or {}
    path = os.path.join(SOURCES, document.collection, meta.get("source_file") or "")
    if not meta.get("source_file") or not os.path.exists(path):
        return None
    if path not in _source_roots:
        _source_roots[path] = {el.get("id"): el for el in _read_thml(path).iter()
                               if el.get("id")}
    div = _source_roots[path].get(chapter_key)
    if div is None:
        return None
    lines = [_block_text(b) for b in direct_blocks(div)]
    return [line for line in lines if line][:8]


def letter_sender(document: Document, letter: list) -> str | None:
    """The sender of one letter, from the editor's title line (the paragraph after the
    "Epistle N." line), or None when the letter has no such lines, the title line
    addresses someone ("To …"), or the title or the greeting opens with the document's
    author ("Cyprian to the Lapsed"; "1. Cyprian to Cæcilius"). The lines are the
    source's (`source_letter_lines`) where it is at hand, else the passages'."""
    lines = source_letter_lines(document, letter[0].chapter_key)
    if lines is None:
        lines = [line for p in letter for line in _paragraphs(p.content)][:8]
    number = next((i for i, line in enumerate(lines[:4]) if LETTER_NUMBER_LINE.match(line)), None)
    if number is None or number + 1 >= len(lines):
        return None
    title = lines[number + 1]
    greeting = next((line for line in lines[number + 2:] if not line.startswith("Argument")), "")
    author = _fold(document.author or "").split(" ")[0]
    if title.startswith("To ") or _fold(title).split(" ")[0] == author \
            or _fold(greeting.lstrip("0123456789. ")).split(" ")[0] == author:
        return None
    m = _TITLE_SENDER.match(title)
    return m.group("sender").strip(" ,.") if m else title


def letter_senders(collection: str, documents: list[Document]) -> Failures:
    out: Failures = {}
    for d in documents:
        if not LETTER_COLLECTION.match(d.title):
            continue
        keys = []
        for key, group in itertools.groupby(d.passages, key=lambda p: p.chapter_key):
            letter = list(group)
            if not LETTER_CHAPTER.match(letter[0].chapter_label):
                continue
            sender = letter_sender(d, letter)
            if sender is None:
                continue
            first = _fold(sender).split(" ")[0]
            if any(first not in _fold(resolved_author(d, p)).split(" ") for p in letter):
                keys.append(key)
        if keys:
            out[f"attribution.letter_sender:{collection}/{d.id}"] = keys
    return out


_NARRATIVE = re.compile(r"^(?:The )?(?:Martyrdom|Passion|Acts) of (?:the )?(?:Holy )?(?P<name>.+?)\.?$")


def narrative_of_author_death(works: list[dict]) -> Failures:
    """Work registry rows (and the works inside them) titled as the narrative of a
    death whose credited author is the person it names, with no note."""
    out: Failures = {}
    for row in works:
        entries = [(row["title"], (row.get("attribution") or {}).get("credited_as") or row.get("author"),
                    (row.get("attribution") or {}).get("basis"))]
        entries += [(w.get("title") or "", w.get("author") or row.get("author"),
                     w.get("notes") or w.get("attribution_note")) for w in row.get("works", [])]
        for title, author, note in entries:
            m = _NARRATIVE.match(title or "")
            if m and author and not note and _fold(author) == _fold(m.group("name")):
                out[f"attribution.narrative_of_author_death:{row['collection']}/{row['document_id']}"] = [title]
    return out


def load_works(path: str = WORKS_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- labels

def reference_author_consistent(collection: str, documents: list[Document]) -> Failures:
    """ThML references read "<author> — <title>, <label>"; the author part must be the
    passage's resolved display author. A reference with no author part passes."""
    out: Failures = {}
    for d in documents:
        anchors = []
        for p in d.passages:
            named, sep, _ = p.reference.partition(" — ")
            if sep and _fold(named) != _fold(resolved_author(d, p)):
                anchors.append(p.anchor)
        if anchors:
            out[f"labels.reference_author_consistent:{collection}/{d.id}"] = anchors
    return out


_TITLE_CASED = re.compile(r"\b[IVXLC][ivxlc]+\b")
_VALID_ROMAN = re.compile(r"^(?=[IVXLC])C{0,3}(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$")


def roman_case(collection: str, documents: list[Document]) -> Failures:
    """Chapter and unit labels holding a title-cased Roman numeral ("Ii.", "Xiv"): a word
    of Roman-numeral letters, capital first, that is a valid numeral in capitals. Real
    words that are not valid numerals ("Civil", "Ill") are not flagged."""
    out: Failures = {}
    for d in documents:
        anchors = [p.anchor for p in d.passages
                   if any(_VALID_ROMAN.match(w.upper())
                          for label in (p.chapter_label, p.unit_label or "")
                          for w in _TITLE_CASED.findall(label))]
        if anchors:
            out[f"labels.roman_case:{collection}/{d.id}"] = anchors
    return out


# Collections whose adapters do not yet cite each piece on its own (1.6).
UNIQUE_REFERENCE_PENDING = ("catechism",)


def unique_references(collection: str, documents: list[Document]) -> Failures:
    out: Failures = {}
    for d in documents:
        shared = sorted(r for r, n in Counter(p.reference for p in d.passages).items() if n > 1)
        if shared:
            out[f"labels.unique_reference:{collection}/{d.id}"] = shared
    return out


def unique_titles(collection: str, documents: list[Document]) -> Failures:
    titles = Counter(_fold(d.title) for d in documents)
    shared = sorted(t for t, n in titles.items() if n > 1)
    return {f"registry.unique_title_per_collection:{collection}": shared} if shared else {}


# --------------------------------------------------------------------------- canon law

# A lowercase word with a capital V or Y inside it, or one opening a lowercase word after
# a lowercase-free start ("Vnal"): the source's lost "ff" and "ffi" ligatures.
LIGATURE_CORRUPTION = re.compile(r"\b[a-z]+[VY][a-z]*\b|\b[VY][a-z]*[VY][a-z]+\b")


def canon_ligature_corruption(documents: list[Document]) -> Failures:
    canons = []
    for d in documents:
        for p in d.passages:
            if LIGATURE_CORRUPTION.search(p.content):
                canons.append(str((p.metadata or {}).get("canon") or p.anchor))
    return {"text.canon_law.ligature_corruption:canon-law": canons} if canons else {}


# --------------------------------------------------------------------------- entry point

def run(collection: str, documents: list[Document], *, corrections: dict | None = None,
        works: list[dict] | None = None) -> Failures:
    """Every failing content check for one collection."""
    out: Failures = {}
    if collection == "summa":
        corrections = load_summa_corrections() if corrections is None else corrections
        out.update(summa_objection_after_replies(documents))
        out.update(summa_sed_contra_boundaries(documents, corrections))
        out.update(summa_adjacent_duplicates(documents))
        out.update(summa_unbold_openings(documents))
        out.update(summa_editor_supplied(documents, corrections))
        out.update(summa_reply_targets(documents, corrections))
        out.update(summa_reference_has_question(documents))
    if collection in THML_COLLECTIONS:
        out.update(argument_lines(collection, documents))
        out.update(chapter_title_lines(collection, documents))
        out.update(provenance_lines(collection, documents))
        out.update(letter_senders(collection, documents))
        out.update(reference_author_consistent(collection, documents))
    if collection == "canon-law":
        out.update(canon_ligature_corruption(documents))
    out.update(roman_case(collection, documents))
    if collection not in UNIQUE_REFERENCE_PENDING:
        out.update(unique_references(collection, documents))
    out.update(unique_titles(collection, documents))
    works = load_works() if works is None else works
    out.update(narrative_of_author_death([w for w in works if w.get("collection") == collection]))
    return out
