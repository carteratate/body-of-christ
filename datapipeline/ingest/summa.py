"""Summa Theologica ingestion → one Document, one passage per article part.

SOURCE NOTE (leader-dot artifact): the NPNF source XML flattened a 3-column
comparison table into runs of ". . . . ." leader dots in a few articles (the
text before reads "may be seen from the following diagram"). These long runs
are collapsed by normalize.text.normalize_ellipses(). The cryptic reference
apparatus (Q[7], AA[3], FP/TP, QQ[1]-114, [*Cf. ...], "Question. N") is expanded
by normalize.summa.expand_apparatus() and shouting titles by title_case_shouting.

Structure: Part (div1) → Treatise (div2) → Question (div3) → Article (div4).
Each article is read paragraph by paragraph into its dialectical parts (Objection N /
On the contrary / I answer that / Reply to Objection N), each a sub-passage of the
article's reader chapter; a part longer than a card is packed from its paragraphs
(`ingest.pieces`). A question's own prologue, the paragraphs before its first article,
is a passage of its own chapter before Article 1 (Decision log "Summa question
prologues (1.7)"), and so are the treatise prologues of I-II and III.

A paragraph's role comes from R7's reviewed corrections file first
(`summa_corrections.json`, docs/research/R7-summa-structure.md section 8), then from its
bold marker, then from a canonical opening of an unbold paragraph. A phrase inside a
paragraph never starts a part, except where the corrections file says one does
(`parts`). Unmarked paragraphs join the part before them (C-04, C-14).

Anchors come from the source's own ids, never from a part label or an article title
(2.1, Decision log "Summa anchors (2.1)"): a part is `summa/<div id>/<paragraph>`,
named by the source paragraph it opens with (`FP_Q29_A2-p5` is `summa/FP_Q29_A2/p5`),
with `-2` when it opens inside a paragraph. A unit CCEL lost, restored from a printed
edition (`summa_recovered.json`), is `summa/<article>/recovered-<n>`. So every
correction of a role, number, chapter or citation keeps the passage's ID (D1).
"""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field

import defusedxml.ElementTree as ET

from config import settings
from identity import anchor as make_anchor
from model import ContentsNode, Document, Passage, Work
from normalize.text import clean_text
from normalize.caps import roman_capitals, title_case_shouting
from normalize.summa import expand_apparatus
from ingest.common import _block_text
from ingest.pieces import Segment, SourceMap, name_pieces, pack_units, piece_reference
from registry import ANCHOR_SCHEME, resolve_document_id

_HERE = os.path.dirname(__file__)
_SRC = os.path.join(os.path.dirname(_HERE), "sources", "summa", "summa.xml")
CORRECTIONS = os.path.join(_HERE, "summa_corrections.json")
RECOVERED = os.path.join(_HERE, "summa_recovered.json")

# The citation's name for each part, by the prefix of its div ids (1.7 spec, References).
PART_CITATION = {"FP": "I", "FS": "I-II", "SS": "II-II", "TP": "III", "XP": "Suppl.",
                 "AP1": "Suppl., App. 1", "AP2": "Suppl., App. 2"}
# The part's clean name, by its div1 id, for metadata `part`.
PART_NAME = {"FP": "First Part", "FS": "First Part of the Second Part",
             "SS": "Second Part of the Second Part", "TP": "Third Part",
             "XP": "Supplement to the Third Part", "vii": "Appendix"}
# The Supplement and its appendix, compiled after Aquinas's death, are works of their own
# inside the Summa (3.2, D6), keyed by their div1 id; the registry gives them their note.
PART_WORKS = (Work(work_key="XP", ordinal=1, title=PART_NAME["XP"]),
              Work(work_key="vii", ordinal=2, title="Appendix to the Supplement"))
_PART_WORK_KEYS = frozenset(w.work_key for w in PART_WORKS)
# Divs that hold the parts' text. The title page (`i`) and indexes (`viii`) do not.
_PART_DIVS = tuple(PART_NAME)
# Treatise-level divs written by editors, not Aquinas (rule G): the Supplement's
# "Editor's note" and Nicolai's note before the appendix. They stay out.
_EDITORIAL_DIVS = frozenset({"XP.i", "vii.i"})
# Units the translators' base text has and the Leonine edition lacks, removed as text
# outside the Leonine (Carter, 12 Nov 2026, R7 question 3): III q.57 a.4's objection 2
# and its reply, and III q.22 a.2's reply 3 with the note introducing it. III q.55
# a.6's objection 5 stays: the Leonine prints its reply.
OUTSIDE_LEONINE = frozenset({"TP_Q57_A4-p3", "TP_Q57_A4-p4", "TP_Q57_A4-p11",
                             "TP_Q57_A4-p12", "TP_Q22_A2-p12", "TP_Q22_A2-p13"})
# The printed "Objection N: On the contrary" sed contras Aquinas grants rather than
# answers ("Quartum concedimus"): they are not a view he rejects (Carter, 12 Nov 2026).
GRANTED = frozenset({"SS_Q123_A12-p5", "SS_Q136_A5-p5"})
# Article titles whose printed number disagrees with their div id; the id wins. Any
# other disagreement fails the build. I q.114 a.5 is titled "Article. 4" (#251).
_MISNUMBERED_TITLES = frozenset({"FP_Q114_A5"})

_DIV_ID = re.compile(r"^(FP|FS|SS|TP|XP|AP1|AP2)_Q(\d+)(?:_A(\d+))?$")
_BOLD = re.compile(r"^(?:Objection (\d+)[:.]|Reply to Objection (\d+):|On the contrary,|"
                   r"I answer that,)")
# Canonical openings of an unbold paragraph (C-14), with or without the comma: R7's
# corrections file lists every comma-less one in the four core parts, and four more
# open Supplement paragraphs ("I answer that There are two reasons", XP q.11 a.4).
_OPENING = re.compile(r"^(?:On the contrary\b|I answer that\b|The contrary, however|"
                      r"(?:Reply|Replies) OBJ (\d+)|OBJ (\d+)\.)")
# An unbold "Reply OBJ 2 and 3:" marker, removed from the text when it is a label.
_OBJ_MARKER = re.compile(r"^(?:(?:Reply|Replies) )?OBJ [\d ,and]+[:.]\s*")
_ARTICLE_TITLE = re.compile(r"^Article\s*(\d+)\s*-\s*")
_QUESTION_TITLE = re.compile(r"^Question\s*\d+\s*-\s*")
_ARTICLE_COUNT = re.compile(r"\s*\((?:[A-Za-z]+|\d+) Articles?\)\s*$", re.IGNORECASE)
_LETTER = re.compile(r"[^\W\d_]")
_AD = re.compile(r"\bad (\d+)(?:(?:, ?| et )(\d+))?")
_SC_NUMBER = re.compile(r"\bs\. c\. (\d+)")

ROLE_LABELS = {"sed-contra": "On the contrary", "determination": "I answer that"}


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", f.read(), flags=re.DOTALL)
    return ET.fromstring(xml)


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- citations

def _numbers_phrase(numbers: list[int]) -> str:
    """"4", "2 and 3", "1, 2 and 3"."""
    words = [str(n) for n in numbers]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _citation(div_id: str, label: str | None, cited: str | None = None) -> str:
    """"Summa Theologiae II-II, q. 83, a. 14, ad 2": the part from the div id's prefix,
    the question and article numbers from the id (a question's div names article 1, a
    one-article question), and the part's suffix from its label, or `cited` where the
    Latin role differs from the printed label. A prologue cites "…, q. 2, prologue"; a
    treatise prologue, which has no question, "Summa Theologiae I-II, prologue"."""
    m = _DIV_ID.match(div_id)
    if not m:
        part = div_id.split(".", 1)[0]
        return f"Summa Theologiae {PART_CITATION[part]}, prologue"
    part, q, a = m.group(1), m.group(2), m.group(3)
    base = f"Summa Theologiae {PART_CITATION[part]}, q. {q}"
    if label and label.startswith("Question") and label.endswith("prologue"):
        return f"{base}, prologue"
    base = f"{base}, a. {a or 1}"
    suffix = cited or _label_suffix(label)
    return f"{base}, {suffix}" if suffix else base


def _label_suffix(label: str | None) -> str | None:
    if not label:
        return None
    if label.startswith("Objection"):
        return "obj. " + label.split()[-1]
    if label == "On the contrary":
        return "sed contra"
    if label == "I answer that":
        return "co."
    if label.startswith("Reply to Objection"):
        return "ad " + label.split(" ", 3)[3]
    return None


# --------------------------------------------------------------------------- paragraphs

@dataclass
class _Para:
    pid: str                  # the source id, "FP_Q29_A2-p5"; "recovered-1" for a unit
    text: str                 # raw text, without tags, after any in-place restoration
    bold: str = ""            # the bold marker it opens with, if any
    facts: dict = field(default_factory=dict)   # its corrections-file entry

    @property
    def locator(self) -> str:
        return self.pid.rsplit("-", 1)[1] if "-p" in self.pid else self.pid

    @property
    def div(self) -> str:
        return self.pid.rsplit("-", 1)[0]


@dataclass
class _Part:
    role: str | None          # objection, sed-contra, determination, reply, or None
    label: str | None
    paras: list[_Para]
    cited: str | None = None  # the citation suffix, where the Latin role differs
    suffix: str = ""          # "-2" for a part that opens inside its first paragraph
    targets: list[str] = field(default_factory=list)
    voice: str | None = None
    recovered: dict | None = None
    note: str | None = None


def _paragraph(p) -> _Para | None:
    text = _block_text(p)
    if not text:
        return None
    bold = ""
    b = p.find("b")
    if b is not None and not (p.text or "").strip() and list(p).index(b) == 0:
        bold = " ".join("".join(b.itertext()).split())
    return _Para(p.get("id") or "", text, bold)


def _restore_in_place(para: _Para, fixes: dict) -> None:
    fix = fixes.get(para.pid)
    if fix is None:
        return
    if para.text.count(fix["find"]) != 1:
        raise ValueError(f"summa: {para.pid}: restoration text not found exactly once")
    para.text = para.text.replace(fix["find"], fix["replace"])


# --------------------------------------------------------------------------- the walk

def _marker_role(para: _Para) -> tuple[str | None, int | None]:
    """The role and number a paragraph's own marker gives: its bold marker, else a
    canonical opening of an unbold paragraph."""
    m = _BOLD.match(para.bold) if para.bold else None
    if m:
        if m.group(1):
            return "objection", int(m.group(1))
        if m.group(2):
            return "reply", int(m.group(2))
        return ("sed-contra" if para.bold.startswith("On") else "determination"), None
    if para.bold:
        return None, None
    m = _OPENING.match(para.text)
    if not m:
        return None, None
    if m.group(1):
        return "reply", int(m.group(1))
    if m.group(2):
        return "objection", int(m.group(2))
    return ("determination" if m.group(0).startswith("I answer") else "sed-contra"), None


def _strip_label(para: _Para) -> str:
    """The paragraph's text without a marker that is only a label ("Objection 1:",
    "Reply to Objection 2:", "Reply OBJ 2 and 3:"). "On the contrary," and "I answer
    that," stay, as printed (C-27)."""
    text = para.text
    if para.bold and not para.bold.startswith(("On the contrary", "I answer that")):
        return text[text.index(para.bold) + len(para.bold):].strip()
    m = _OBJ_MARKER.match(text)
    if m:
        return text[m.end():].strip()
    if text.startswith(("Reply OBJ ", "Replies OBJ ")):
        # "Reply OBJ 2 is clear from the above.": a sentence, printed "Reply Obj. 2".
        return text.replace(" OBJ ", " Obj. ", 1)
    return text


def _target_numbers(targets: list[str], kind: str) -> list[int]:
    return [int(t.split()[1]) for t in targets if t.startswith(kind + " ")]


def _reply_part(paras: list[_Para], number: int | None) -> _Part:
    """A reply's label, citation and targets: the corrections file's targets and the
    Latin `ad` numbering where it gives them (C-14, Decision log "Summa reply targets
    (1.7)"), else the printed number."""
    facts = paras[0].facts
    number = facts.get("latin_number") or number      # III q.57 a.4, numbered by the Leonine
    targets = list(facts.get("targets") or ([f"obj {number}"] if number else []))
    ad = sorted({int(n) for c in facts.get("latin", []) for g in _AD.findall(c)
                 for n in g if n})
    objections = _target_numbers(targets, "obj")
    if objections and len(objections) == len(targets):
        numbers = objections
    else:
        # A reply to a sed contra: the Leonine numbers it after the objections ("ad 4").
        numbers = ad or ([number] if number else [])
    noun = "Objection" if len(numbers) <= 1 else "Objections"
    label = f"Reply to {noun} {_numbers_phrase(numbers)}" if numbers else "Reply"
    return _Part("reply", label, paras, cited=f"ad {_numbers_phrase(numbers)}" if numbers
                 else None, targets=targets)


def _sed_contra_cited(facts: dict) -> str | None:
    numbered = [int(n) for c in facts.get("latin", []) for n in _SC_NUMBER.findall(c)]
    return f"sed contra {numbered[0]}" if numbered and numbered[0] > 1 else None


def _opening_part(para: _Para, role: str | None, number: int | None) -> _Part:
    facts = para.facts
    if facts.get("latin_role") == "sed-contra":
        # The translators' "Objection 4: On the contrary": the printed label and number
        # stay; the citation gives the Latin role (Carter, 12 Nov 2026, R7 question 1).
        n = facts.get("latin_number")
        many = any(_SC_NUMBER.search(c) for c in facts.get("latin", []))
        return _Part("objection", f"Objection {number}", [para],
                     cited=f"sed contra {n}" if many and n else "sed contra",
                     voice=None if para.pid in GRANTED else "rejected")
    if role == "objection":
        n = facts.get("latin_number") or facts.get("number") or number
        return _Part("objection", f"Objection {n}", [para], voice="rejected")
    if role == "reply":
        return _reply_part([para], facts.get("number") or number)
    if role == "sed-contra":
        return _Part(role, ROLE_LABELS[role], [para], cited=_sed_contra_cited(facts))
    return _Part(role, ROLE_LABELS.get(role), [para])


def _split_inside(para: _Para, parts_spec: list[dict]) -> list[tuple[_Para, dict]]:
    """A paragraph holding more than one part (`parts`, R7): cut where each later part
    opens, each piece a paragraph of its own whose locator carries the anchor suffix."""
    out, rest = [], para.text
    cuts = []
    for spec in parts_spec[1:]:
        at = rest.find(spec["opens_with"], cuts[-1][0] + 1 if cuts else 1)
        if at < 0:
            raise ValueError(f"summa: {para.pid}: no {spec['opens_with']!r} to open a part")
        cuts.append((at, spec))
    starts = [0] + [at for at, _ in cuts]
    ends = starts[1:] + [len(rest)]
    specs = [parts_spec[0]] + [s for _, s in cuts]
    for k, (a, b, spec) in enumerate(zip(starts, ends, specs)):
        text = rest[a:b].strip()
        bold = para.bold if k == 0 else ""
        if spec["opens_with"][0].islower():
            text = text[0].upper() + text[1:]       # "on the contrary," as printed
        piece = _Para(para.pid, text, bold, para.facts if k == 0 else {})
        out.append((piece, spec))
    return out


def article_parts(paras: list[_Para], facts: dict | None = None,
                  recovered: list[dict] | None = None) -> list[_Part]:
    """The parts of one article, read paragraph by paragraph (1.7, C-04, C-14).

    `paras` are the article's paragraphs in order, each with its corrections-file entry
    and with the corrections' exclusions already applied. `facts` is the article's entry
    (`reply_only`, `unmarked_determination`). `recovered` are whole units restored from
    a printed edition, each placed after the paragraph its `after` names."""
    facts = facts or {}
    after: dict[str, list[dict]] = {}
    for n, unit in enumerate(recovered or [], 1):
        after.setdefault(unit["after"], []).append({**unit, "n": n})
    parts: list[_Part] = []
    seen_sed_contra = False
    unmarked = facts.get("unmarked_determination")
    for para in paras:
        spec = para.facts.get("parts")
        pieces = _split_inside(para, spec) if spec else [(para, None)]
        for k, (piece, piece_spec) in enumerate(pieces):
            if piece_spec is not None:
                role = piece_spec["role"]
                number = _marker_role(piece)[1] if k == 0 else None
            else:
                role = piece.facts.get("role")
                number = None
                if role is None or role in ("objection", "reply"):
                    marked, number = _marker_role(piece)
                    role = role or marked
            if role is None and unmarked and seen_sed_contra and piece.pid == unmarked:
                role = "determination"
            if role is None and parts:
                parts[-1].paras.append(piece)
                continue
            part = _opening_part(piece, role, number)
            if k:
                part.suffix = piece_spec.get("anchor_suffix", f"-{k + 1}")
            seen_sed_contra = seen_sed_contra or role == "sed-contra"
            parts.append(part)
        for unit in after.get(para.pid, []):
            parts.append(_recovered_part(unit))
    _answer_sed_contras(parts)
    for part in parts:
        answered = [t for p in part.paras for t in p.facts.get("also_answers", [])]
        part.targets += [t for t in answered if t not in part.targets]
    return parts


def _answer_sed_contras(parts: list[_Part]) -> None:
    """A reply numbered past the article's last objection answers a sed contra argument:
    the Leonine numbers those replies after the objections, so with three objections
    "ad 4" answers the first (R7 section 3; C-29). R7's corrections file records them for
    the four core parts; this reads the same rule where it records none (the
    Supplement)."""
    objections = [int(p.label.split()[-1]) for p in parts if p.role == "objection"]
    if not objections or not any(p.role == "sed-contra" for p in parts):
        return
    last = max(objections)
    for part in parts:
        facts = part.paras[0].facts
        if part.role != "reply" or facts.get("targets") or len(part.targets) != 1:
            continue
        kind, n = part.targets[0].split()
        if kind == "obj" and int(n) > last:
            part.targets = [f"sc {int(n) - last}"]


def _recovered_part(unit: dict) -> _Part:
    kind, n = unit["unit"].split()
    para = _Para(f"recovered-{unit['n']}", unit["text"])
    if kind == "obj":
        part = _Part("objection", f"Objection {n}", [para], voice="rejected")
    elif kind == "ad":
        part = _Part("reply", f"Reply to Objection {n}", [para], cited=f"ad {n}",
                     targets=[f"obj {n}"])
    else:
        part = _Part("sed-contra", ROLE_LABELS["sed-contra"], [para],
                     cited=f"sed contra {n}" if int(n) > 1 else None)
    part.recovered = unit
    return part


# --------------------------------------------------------------------------- the build

@dataclass
class _Build:
    corrections: dict
    recovered: dict
    maxc: int
    passages: list[Passage] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    # For the contents tree: the chapter each emitted unit opens, by its node key (an
    # article's or treatise prologue's div id, "<question id>/prologue"), and each
    # question's articles in reading order as (div id, number, title).
    chapters: dict[str, str] = field(default_factory=dict)
    articles: dict[str, list[tuple[str, int, str]]] = field(default_factory=dict)

    def emit(self, parts: list[_Part], *, div_id: str, part_code: str, ch_key: str,
             ch_label: str, question: str | None, article: str | None,
             cite_div: str, node: str) -> None:
        editions = self.recovered.get("editions", {})
        first = True
        for part in parts:
            units = [(None, clean_text(expand_apparatus(_strip_label(p) if i == 0 else p.text)))
                     for i, p in enumerate(part.paras)]
            segments = [Segment(p.locator, p.text) for p in part.paras]
            units = [(None, t) for _, t in units if t]
            text = "\n\n".join(t for _, t in units).strip()
            if not _LETTER.search(text):
                self.dropped.append(part.paras[0].pid)
                continue
            if part.recovered:
                unit = f"summa/{div_id}/{part.paras[0].pid}"
            else:
                unit = f"summa/{part.paras[0].div}/{part.paras[0].locator}{part.suffix}"
            pieces = [p.text for p in pack_units(units, self.maxc)]
            named = name_pieces(unit, text, pieces, segments, SourceMap(text, segments))
            base = _citation(cite_div, part.label, part.cited)
            if question:
                base = f"{base}: {question}"
            metadata: dict = {"part": PART_NAME[part_code]}
            if article:
                metadata["article"] = article
            if part.role == "reply" or part.targets:
                metadata["reply_targets"] = part.targets
            if part.recovered:
                edition = editions[part.recovered["source"]]
                metadata["recovered_from"] = (f"{edition['edition']}, p. "
                                              f"{part.recovered['page']}")
            for k, (piece, (anchor, source_units)) in enumerate(zip(pieces, named), 1):
                self.passages.append(Passage(
                    content=piece, anchor=anchor,
                    reference=piece_reference(base, None, None, k, len(pieces)),
                    chapter_key=ch_key, chapter_label=ch_label,
                    position=len(self.passages), unit_label=part.label,
                    metadata=dict(metadata), voice=part.voice,
                    note=part.note if first else None, source_units=source_units,
                    work_key=part_code if part_code in _PART_WORK_KEYS else None))
                self.chapters.setdefault(node, ch_key)
                first = False


def _title(div) -> str:
    return expand_apparatus(title_case_shouting((div.get("title") or "").strip()))


def _question_text(q: str) -> str:
    """"Question 71 - On the Work of the Fifth Day (One Article)" → "On the Work of the
    Fifth Day": what a one-article question's citation asks."""
    return _ARTICLE_COUNT.sub("", _QUESTION_TITLE.sub("", q)).strip()


def _article_title(div_id: str, title: str) -> tuple[int, str]:
    """The article's number, from its div id, and its title with that number. A title
    whose printed number disagrees with the id fails the build, except I q.114 a.5."""
    number = int(_DIV_ID.match(div_id).group(3))
    m = _ARTICLE_TITLE.match(title)
    if m and int(m.group(1)) != number:
        if div_id not in _MISNUMBERED_TITLES:
            raise ValueError(f"summa: {div_id} is titled {title[:12]!r}")
        title = f"Article {number} - {title[m.end():]}"
    return number, title


def _kept(b: _Build, paras: list[_Para]) -> list[_Para]:
    """The paragraphs the walk reads, each with its corrections-file entry."""
    corrections = b.corrections["paragraphs"]
    kept = []
    for para in paras:
        para.facts = corrections.get(para.pid, {})
        if _excluded(b, para):
            continue
        kept.append(para)
    return kept


def _excluded(b: _Build, para: _Para) -> bool:
    """Editorial scope first (C-04): editors' text, an editor-supplied reply, units
    outside the Leonine and the second copy of a duplicated paragraph never reach the
    walk, so they cannot join or revive a part. Each is in the removal registry."""
    facts = para.facts
    flag = facts.get("flag")
    why = None
    if flag in ("editorial", "editor-supplied") or facts.get("role") == "editorial":
        why = flag or "editorial"
    elif para.pid in OUTSIDE_LEONINE:
        why = "not-in-leonine"
    elif facts.get("role") == "duplicate":
        why = "duplicate"
    elif facts.get("role") == "article-title":
        why = "article-title"
    if why:
        b.excluded.append({"paragraph": para.pid, "why": why})
    return why is not None


def build_document(path: str | None = None, corrections: dict | None = None,
                   recovered: dict | None = None) -> Document:
    root = _read_root(path or _SRC)
    corrections = copy.deepcopy(_load(CORRECTIONS) if corrections is None else corrections)
    recovered = _load(RECOVERED) if recovered is None else recovered
    b = _Build(corrections, recovered, settings.MAX_PASSAGE_CHARS)
    fixes = {f["paragraph"]: f for f in recovered.get("in_place", [])}
    for pid, fix in fixes.items():
        if fix.get("parts"):
            corrections["paragraphs"].setdefault(pid, {})["parts"] = fix["parts"]
    units_by_article: dict[str, list[dict]] = {}
    for unit in recovered.get("units", []):
        units_by_article.setdefault(unit["article"], []).append(unit)
    articles = corrections.get("articles", {})
    moved_to = {pid: facts["move_to"] for pid, facts in corrections["paragraphs"].items()
                if facts.get("move_to")}

    def paragraphs(elems) -> list[_Para]:
        out = []
        for p in elems:
            para = _paragraph(p)
            if para is not None:
                _restore_in_place(para, fixes)
                out.append(para)
        return out

    for div1 in root.iter("div1"):
        code = div1.get("id")
        if code not in _PART_DIVS:
            continue
        part_title = _title(div1)
        for div2 in div1.iter("div2"):
            prologue = [p for p in div2 if p.tag == "p"]
            if prologue and div2.get("id") not in _EDITORIAL_DIVS:
                key = make_anchor("summa", part_title, "prologue")
                parts = [_Part(None, "Prologue", paragraphs(prologue))]
                b.emit(parts, div_id=div2.get("id"), part_code=code, ch_key=key,
                       ch_label="Prologue", question=None, article=None,
                       cite_div=div2.get("id"), node=div2.get("id"))
        for div3 in div1.iter("div3"):
            q_id = div3.get("id") or ""
            q = _title(div3)
            div4s = list(div3.iter("div4"))
            if not div4s and not _DIV_ID.match(q_id):
                # The Prologue of I-II (FS.i.i): a treatise prologue, not a question.
                key = make_anchor("summa", part_title, "prologue")
                parts = [_Part(None, "Prologue", paragraphs(div3.iter("p")))]
                b.emit(parts, div_id=q_id, part_code=code, ch_key=key, ch_label="Prologue",
                       question=None, article=None, cite_div=q_id, node=q_id)
                continue
            q_number = int(_DIV_ID.match(q_id).group(2))
            if div4s:
                head = []
                for child in div3:
                    if child.tag == "div4":
                        break
                    if child.tag == "p":
                        head.append(child)
                body = []
            else:
                # A one-article question (I q.71, q.72): its prologue is the unmarked
                # paragraphs before the first marker, its article the rest.
                all_paras = paragraphs(div3.iter("p"))
                for para in all_paras:
                    para.facts = corrections["paragraphs"].get(para.pid, {})
                first = next((i for i, p in enumerate(all_paras) if _marker_role(p)[0]),
                             len(all_paras))
                head, body = all_paras[:first], all_paras[first:]
            head_paras = paragraphs(head) if div4s else head
            if head_paras:
                label = f"Question {q_number}, prologue"
                b.emit([_Part(None, label, head_paras)], div_id=q_id, part_code=code,
                       ch_key=make_anchor("summa", part_title, q, "prologue"),
                       ch_label=f"{q} — Prologue", question=None, article=None,
                       cite_div=q_id, node=f"{q_id}/prologue")
            if not div4s:
                kept = _kept(b, body)
                question = " ".join(_question_text(q).split())
                b.emit(article_parts(kept, articles.get(q_id), units_by_article.get(q_id)),
                       div_id=q_id, part_code=code,
                       ch_key=make_anchor("summa", part_title, q, "article-1"),
                       ch_label=f"{q} — Article 1 - {question}", question=question,
                       article=q_id, cite_div=q_id, node=f"{q_id}_A1")
                b.articles.setdefault(q_id, []).append((f"{q_id}_A1", 1, question))
                continue
            for div4 in div4s:
                _build_article(b, div4, code, part_title, q, articles, moved_to,
                               units_by_article, paragraphs)
    metadata = {"source_file": "summa.xml", "source_key": "summa",
                "anchor_scheme": ANCHOR_SCHEME}
    if b.excluded:
        metadata["excluded_paragraphs"] = b.excluded
    if b.dropped:
        metadata["dropped_empty_parts"] = b.dropped
    return Document(id=resolve_document_id("summa", "summa", ("summa",)), collection="summa",
                    title="Summa Theologiae", author="Thomas Aquinas", metadata=metadata,
                    passages=b.passages, contents=build_contents(root, b),
                    works=[w for w in PART_WORKS
                           if any(p.work_key == w.work_key for p in b.passages)])


def _build_article(b: _Build, div4, code: str, part_title: str, q: str, articles: dict,
                   moved_to: dict, units_by_article: dict, paragraphs) -> None:
    article = div4.get("id")
    if not article:
        raise ValueError(f"summa: an article of {q!r} has no div id to anchor on")
    a_title = _title(div4)
    number, a_title = _article_title(article, a_title)
    paras = paragraphs(div4.iter("p"))
    # Two articles in one div (C-07): the trailing article's paragraphs, from its title
    # paragraph on, are their own article (`move_to`), keeping their anchors (D1).
    groups: list[tuple[str, list[_Para]]] = [(article, [])]
    for para in paras:
        target = moved_to.get(para.pid)
        if target and target != groups[-1][0]:
            groups.append((target, []))
        groups[-1][1].append(para)
    for art_id, members in groups:
        title_text = a_title
        if art_id != article:
            heading = next(p for p in members
                           if b.corrections["paragraphs"].get(p.pid, {}).get("role")
                           == "article-title")
            n = int(_DIV_ID.match(art_id).group(3))
            title_text = f"Article {n} - {clean_text(expand_apparatus(heading.text))}"
        question = " ".join(_ARTICLE_TITLE.sub("", title_text).split())
        kept = _kept(b, members)
        facts = articles.get(art_id, {})
        parts = article_parts(kept, facts, units_by_article.get(art_id))
        note = _missing_note(facts, b.recovered)
        if note and parts:
            parts[0].note = note
        b.emit(parts, div_id=art_id, part_code=code,
               ch_key=make_anchor("summa", part_title, q, title_text),
               ch_label=f"{q} — {title_text}".strip(" —"), question=question or None,
               article=art_id, cite_div=art_id, node=art_id)
        b.articles.setdefault(art_id.rsplit("_A", 1)[0], []).append(
            (art_id, int(_DIV_ID.match(art_id).group(3)), question))


def _missing_note(facts: dict, recovered: dict) -> str | None:
    """A reader note for a unit no English edition supplies (Decision log "The Summa
    against an independent edition (R7)"): the article's first passage says it is
    missing. Units restored from a printed edition, whole or in place, need none."""
    restored = {(u["article"], u["unit"]) for u in recovered.get("units", [])}
    in_place = {f["paragraph"].rsplit("-", 1)[0] for f in recovered.get("in_place", [])}
    lost = [m for m in facts.get("missing", [])
            if m["after"].rsplit("-", 1)[0] not in in_place
            and (m["after"].rsplit("-", 1)[0], m["unit"]) not in restored]
    if not lost:
        return None
    if all(m["unit"].startswith("ad (general)") for m in lost):
        return ("The Latin text ends this article with a short reply to all the "
                "objections together, which the English translation does not print.")
    names = ", ".join(m["unit"] for m in lost)
    return f"The English translation omits part of this article's Latin text ({names})."


# --------------------------------------------------------------------------- contents tree

# The tree's name for each part, by its div1 id: (numeral, name) for "I · First Part".
# The numerals are the citation's (PART_CITATION).
PART_TREE = {"FP": ("I", PART_NAME["FP"]), "FS": ("I-II", PART_NAME["FS"]),
             "SS": ("II-II", PART_NAME["SS"]), "TP": ("III", PART_NAME["TP"]),
             "XP": (PART_CITATION["XP"], PART_NAME["XP"]),
             "vii": ("App.", "Appendix to the Supplement")}
# What the Supplement and its appendix add to their range line (3.2's work note).
_PART_NOTE = {"XP": "compiled after Aquinas's death from his earlier writings",
              "vii": "compiled after Aquinas's death from his earlier writings"}
# Treatise ranges the source prints wrongly, as {div id: (printed, held)}; any other
# disagreement between a printed range and the questions a treatise holds fails the
# build. II-II's "Cardinal Virtues" prints the range of both its treatises (its
# fortitude and temperance are the next div2), and the Supplement's "Last Things"
# starts at q.86, the Resurrection's last question.
_RANGE_CORRECTIONS = {"SS.ii": ((47, 170), (47, 122)), "XP.iv": ((86, 99), (87, 99))}

# "(QQ[2-26])", "(QQ[50]-64)", "(Q[1])", "(Q[48-49])", "(QQ 90-108)", "(QQ[1 - 68])".
_PRINTED_RANGE = re.compile(r"\(\s*QQ?\s*\[?\s*(\d+)\s*\]?\s*(?:-\s*\[?\s*(\d+)\s*\]?\s*)?\)")
_SOURCE_NOTE = re.compile(r"\s*\[\*.*\]\s*$")
_SMALL_WORDS = frozenset({"a", "an", "and", "as", "at", "by", "for", "from", "in", "into",
                          "of", "on", "or", "the", "to", "with"})
_SHOUTED = re.compile(r"\b[A-Z][A-Z'’]+\b")
_SMALL_WORD = re.compile(r"(?<=\s)(" + "|".join(sorted(_SMALL_WORDS)) + r")\b", re.IGNORECASE)


def _plain(text: str) -> str:
    """A heading without the translators' trailing note ("[*Strife here denotes…]"),
    their note marks ("IRONY*") and doubled spaces."""
    return " ".join(_SOURCE_NOTE.sub("", text).replace("*", "").split())


def _heading(text: str) -> str:
    """Title case for a question or treatise heading, which the source prints in
    capitals ("OF DULIA"), partly ("OF SATISFACTION, As to Its Nature") or with "The"
    capitalized ("Treatise on The One God"). Roman numerals stay capitals."""
    text = _SHOUTED.sub(lambda m: m.group(0).capitalize(), _plain(text))
    text = _SMALL_WORD.sub(lambda m: m.group(0).lower(), text)
    return roman_capitals(text[:1].upper() + text[1:])


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _range(low: int, high: int) -> str:
    return f"Q. {low}" if low == high else f"Qq. {low}–{high}"


def printed_range(title: str) -> tuple[int, int] | None:
    """The question range a treatise title prints, from the source's inconsistent forms,
    or None when it prints none."""
    m = _PRINTED_RANGE.search(title)
    if not m:
        return None
    low = int(m.group(1))
    return low, int(m.group(2) or low)


def _question_heading(div3) -> str | None:
    """The question's title without "Question N -" or its article count. Where the
    source put a section heading in the title ("EVIL HABITS, i.e. VICES AND SINS
    (QQ[71]-89)", the Supplement's own title on its q.1), the question's real title is
    the heading or paragraph after it that ends with the article count."""
    heads = [_QUESTION_TITLE.sub("", _title(div3))]
    for child in div3:
        if child.tag == "div4":
            break
        if child.tag in ("h3", "p"):
            heads.append(expand_apparatus(title_case_shouting("".join(child.itertext()))))
        if len(heads) > 4:
            break
    for head in heads:
        plain = _plain(head)
        if _ARTICLE_COUNT.search(plain):
            return _heading(_ARTICLE_COUNT.sub("", plain))
    return None


def build_contents(root, b: _Build) -> list[ContentsNode]:
    """The Summa's contents tree: Part > Treatise > Question > Article (#254).

    It walks the same divs as the build: a div1 is a Part, a div2 a Treatise, a div3 a
    Question, and its articles are the ones the build emitted (with the three split out
    of shared divs). A question opens its prologue's chapter where it has one. Questions
    in a div2 that is not a treatise (the Supplement's untitled "QQ[1 - 68]") hang under
    their Part, and the appendix's two div2s are sections. The treatise prologues of
    I-II and III are nodes of their Part, before its first treatise. Keys are the
    source's div ids. Argument parts (objections, replies) are not nodes.
    """
    roots: list[ContentsNode] = []
    for div1 in root.iter("div1"):
        code = div1.get("id")
        if code not in PART_TREE:
            continue
        numeral, name = PART_TREE[code]
        children: list[ContentsNode] = []
        numbers: list[int] = []
        for div2 in div1.findall("div2"):
            prologues = [div2.get("id")] + [d.get("id") for d in div2.findall("div3")
                                            if not _DIV_ID.match(d.get("id") or "")]
            for key in prologues:
                if key in b.chapters:
                    children.append(ContentsNode(
                        key=key, kind="prologue", label="Prologue", short_label="Prologue",
                        chapter_key=b.chapters[key]))
            questions = [_question_node(div3, b) for div3 in div2.findall("div3")
                         if _DIV_ID.match(div3.get("id") or "")]
            if not questions:
                continue
            held = [int(_DIV_ID.match(q.key).group(2)) for q in questions]
            numbers += held
            title = div2.get("title") or ""
            if title.lower().startswith("treatise"):
                children.append(_treatise_node(div2, questions, held))
            elif code == "vii":
                label = _heading(title)
                numbered = all(q.short_label.startswith("Q. ") for q in questions)
                children.append(ContentsNode(
                    key=div2.get("id"), kind="section", label=label, short_label=label,
                    chapter_key=questions[0].chapter_key, children=questions,
                    range_label=_range(min(held), max(held)) if numbered else None))
            else:
                children.extend(questions)
        if not children:
            continue
        range_label = _range(min(numbers), max(numbers)) if numbers and code != "vii" else None
        note = _PART_NOTE.get(code)
        if note:
            range_label = f"{range_label} · {note}" if range_label else note[:1].upper() + note[1:]
        roots.append(ContentsNode(
            key=code, kind="part", label=name, short_label=f"{numeral} · {name}",
            chapter_key=children[0].chapter_key, range_label=range_label,
            children=children))
    return roots


def _treatise_node(div2, questions: list[ContentsNode], held: list[int]) -> ContentsNode:
    key = div2.get("id")
    title = div2.get("title") or ""
    low, high = min(held), max(held)
    printed = printed_range(title)
    if key in _RANGE_CORRECTIONS:
        expected, corrected = _RANGE_CORRECTIONS[key]
        if printed != expected:
            raise ValueError(f"summa: treatise {key} now prints {printed}, not {expected}")
        printed = corrected
    if printed is not None and printed != (low, high):
        raise ValueError(f"summa: treatise {key} prints {_range(*printed)} but holds "
                         f"{_range(low, high)}")
    label = _heading(title.split("(", 1)[0])
    return ContentsNode(key=key, kind="treatise", label=label, short_label=label,
                        chapter_key=questions[0].chapter_key, range_label=_range(low, high),
                        children=questions)


def _question_node(div3, b: _Build) -> ContentsNode:
    q_id = div3.get("id")
    articles = []
    for art_id, number, title in b.articles.get(q_id, []):
        if art_id not in b.chapters:
            continue
        title = _plain(title)
        articles.append(ContentsNode(
            key=art_id, kind="article", label=title, short_label=f"Art. {number} · {title}",
            chapter_key=b.chapters[art_id]))
    if not articles:
        raise ValueError(f"summa: question {q_id} has no article chapter for its tree")
    number = _DIV_ID.match(q_id).group(2)
    title = _question_heading(div3)
    if title is None:
        if _QUESTION_TITLE.match(_title(div3)):
            raise ValueError(f"summa: question {q_id} has no title with an article count")
        # The appendix's "TWO ARTICLES ON PURGATORY", a question with no number.
        title = short_label = _heading(_title(div3))
    else:
        short_label = f"Q. {number} · {title}"
    return ContentsNode(
        key=q_id, kind="question", label=title, short_label=short_label,
        chapter_key=b.chapters.get(f"{q_id}/prologue", articles[0].chapter_key),
        range_label=_count(len(articles), "article"), children=articles)
