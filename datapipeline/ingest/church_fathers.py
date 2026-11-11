"""Church Fathers ingestion — one Document per (father, work).

Parses each ANF/NPNF ThML volume into per-work documents with the correct
Church Father as author (not the series editor) and the specific work title.
Works nest to variable depth (work→chapter or work→book→chapter); book-structured
works (City of God, Against Heresies, …) stay ONE document, with the book carried
into the chapter label and metadata (flat sections for now; richer book→chapter
navigation can be layered on later without re-ingesting).

1.8c fixes what the ANF volumes' layout gets wrong: container names taken for authors,
the greetings printed above a letter's first chapter, the two Ignatian recensions printed
side by side, the commentators printed inside Peter of Alexandria's canons, Asterius
Urbanus's text held directly in its work div, and the works inside one document (D6).
"""
from __future__ import annotations

import os
import re
from glob import glob
from xml.etree.ElementTree import Element, tostring

import defusedxml.ElementTree as ET

from model import Document, Work
from normalize.caps import smart_title_case
from normalize.text import fold_ligatures
from ingest.common import (_block_text, _build_parent_map, _cf_skippable, _strip_tags,
                           direct_blocks, iter_chapters)
from ingest.editorial import Editor, strip_editorial_lines
from ingest.thml_doc import ChapterPlan, _chapter_label, distinct_titles, make_doc

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")
_SINGLE_AUTHOR = {"confessions.xml": "Augustine", "incarnation.xml": "Athanasius"}
_AUGUSTINE_FILES = {"city-of-god.xml", "on-the-holy-trinity.xml"}

# ------------------------------------------------------------------ 1.8c: names

# Authors where the ANF div1 title is a container's name, by (file, div1 id). A callable
# takes the work div. The registry keeps every document ID through the relabel.
_AUTHOR_FIX = {
    ("third-century.xml", "iii"): "Tertullian",                # "Tertullian: Part Fourth."
    ("third-century-2.xml", "vii"): "Anonymous",               # "Appendix." (3.2 labels it)
    ("third-century-3.xml", "iv"): "Dionysius of Alexandria",  # "Dionysius."
    ("third-century-3.xml", "vi"): lambda work: _work_title(work),  # "Anatolius and Minor Writers."
    ("second-century.xml", "ii"): "Hermas",                    # "THE PASTOR OF HERMAS"
}
# Titles by (file, work div id).
_TITLE_FIX = {
    ("second-century.xml", "ii.ii"): "The Shepherd: Visions",
    ("second-century.xml", "ii.iii"): "The Shepherd: Commandments",
    ("second-century.xml", "ii.iv"): "The Shepherd: Similitudes",
    ("third-century-3.xml", "ix.iv"): "The Canonical Epistle",
}
_SPELLING = {"Pierus of Alexandria": "Pierius of Alexandria"}

# ------------------------------------------------------------------ 1.8c: greetings

# A work div whose own paragraphs, above its first chapter, are not an opening to emit:
# the text of Lactantius's fragments waits for 5.6a with the other whole works (1.8e,
# Decision log "Whole Fathers works").
_ROOT_TEXT_LATER = frozenset({("third-fourth-century.xml", "iii.vi")})
# "Ignatius, who is also called Theophorus, to the Church which is at Ephesus";
# "Polycarp, and the presbyters with him, to the Church"; "to her who has obtained mercy".
_SALUTATION = re.compile(r"^[A-Z][^.;:]*?,? to (?:the |her |him |[A-Z])")

# ------------------------------------------------------------------ 1.8c: Ignatius

# The seven genuine letters print the shorter recension and the longer side by side: in
# each unit (the greeting and each chapter) the first paragraph is the shorter, the second
# the longer. Only the shorter is emitted; the longer is removed under rule B (D11).
_RECENSIONS = frozenset(("apostolic fathers.xml", f"v.{n}")
                        for n in ("ii", "iii", "iv", "v", "vi", "vii", "viii"))
_RECENSION_SUFFIX = ": Shorter and Longer Versions"
# Units printing one paragraph, by the ANF01 print page: Ephesians prints chapter XX
# twice (the shorter in the left column, p. 58, the longer in the right), and CCEL kept
# only the left column of Romans X (p. 78), which ends "(that is, on the twenty-third day
# of August). … Amen."
_RECENSION_OVERRIDE = {"v.ii.xx": "short", "v.ii.xxi": "long", "v.v.x": "short"}

# ------------------------------------------------------------------ 1.8c: Peter

# Peter of Alexandria's canons, each followed by Balsamon's and Zonaras's commentary.
_COMMENTARY = frozenset({("third-century-3.xml", "ix.iv")})
_COMMENTATORS = ("Balsamon", "Zonaras")
# The editor's heading over the canons, at the top of Canon I.
_CANONS_HEADING = "The Canons of the Blessed Peter"

# ------------------------------------------------------------------ 1.8c: whole works

# Works whose text sits directly in the work div, with no chapter divs: their paragraphs
# are cut at the headings into chapters. 1.8e decides which others join (Carter: none
# before Phase 4).
_WHOLE_WORK_DIVS = frozenset({("third-fourth-century.xml", "v.ii")})
_HEADINGS = frozenset(f"h{n}" for n in range(1, 7))

# ------------------------------------------------------------------ 1.8c: works (D6)

# Container documents, by (file, work div id): the div level that is each work.
_CONTAINERS = {
    ("third-century-3.xml", "iii.iii"): 3,      # Gregory, "Acknowledged Writings"
    ("third-century-3.xml", "iii.iv"): 3,       # Gregory, "Dubious or Spurious Writings"
    ("third-century-2.xml", "iii.iv"): 4,       # Hippolytus, under Part I and Part II
    ("third-century-2.xml", "iii.v"): 3,        # Appendix to the Works of Hippolytus
    ("third-century-2.xml", "iv.iv"): 3,        # Cyprian's Epistles: each letter
    ("third-century-2.xml", "iv.v"): 3,         # The Treatises of Cyprian
    ("third-century-2.xml", "iv.vii"): 3,       # Treatises Attributed to Cyprian
    ("third-fourth-century.xml", "iii.vi"): 3,  # Fragments of Lactantius
}
# Cyprian's Epistles: the letters written by others (C-02), by div id, as (sender,
# recipient), from each letter's title line and greeting. Epistle XXX, Novatian's for
# the Roman clergy, is credited to no one here: 3.1 removes it under rule A.
_LETTER_SENDERS = {
    "iv.iv.ii": ("The Roman clergy", "the clergy of Carthage"),
    "iv.iv.xvi": ("The confessors", "Cyprian"),
    "iv.iv.xviii": ("Caldonius", "Cyprian"),
    "iv.iv.xx": ("Celerinus", "Lucian"),
    "iv.iv.xxi": ("Lucian", "Celerinus"),
    "iv.iv.xxv": ("Moyses, Maximus, Nicostratus and the other confessors", "Cyprian"),
    "iv.iv.xxix": ("The presbyters and deacons at Rome", "Cyprian"),
    "iv.iv.xxxviii": ("Caldonius, Herculanus and others", "Cyprian"),
    "iv.iv.xlv": ("Pope Cornelius", "Cyprian"),
    "iv.iv.xlvii": ("Pope Cornelius", "Cyprian"),
    "iv.iv.xlix": ("Maximus, Urbanus, Sidonius and Macharius", "Cyprian"),
    "iv.iv.lxxiv": ("Firmilian of Caesarea", "Cyprian"),
    "iv.iv.lxxvii": ("Nemesianus, Dativus, Felix and Victor", "Cyprian"),
    "iv.iv.lxxviii": ("Lucius and the brethren with him", "Cyprian"),
    "iv.iv.lxxix": ("Felix, Jader, Polianus and the martyrs at the mines", "Cyprian"),
}
# A work inside a document that is otherwise one work (C-15), by (file, document div):
# {work div: (title, label prefix)}.
_EMBEDDED_WORKS = {
    ("third-fourth-century.xml", "iii.ii"): {
        "iii.ii.viii": ("Epitome of the Divine Institutes", "Epitome")},
}
# Works inside a container that share a title with another there, by work div id:
# Hippolytus's second set of Psalms fragments (from de Magistris) prints "On the Psalms."
# as the first does.
_WORK_TITLE_FIX = {"iii.iv.i.xiv": "On the Psalms: Further Fragments"}
# Book divs whose title omits the word "Book" (On the Apparel of Women prints "II").
_BOOK_FIX = {("third-century.xml", "iii.iii.ii"): "Book II"}


def _strip_doctype(xml: str) -> str:
    return re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        return ET.fromstring(_strip_doctype(f.read()))


def _source_key(filename, work=None) -> str:
    return f"church-fathers/{filename}" + (f"#{work.get('id')}" if work is not None else "")


def _make_doc(filename, author, title, chapters, work=None, editor=None, works=None):
    """`work` is the div holding the work when the file holds several."""
    return make_doc(collection="church-fathers", filename=filename, author=author,
                    title=title, chapters=chapters, source_key=_source_key(filename, work),
                    editor=editor, works=works)


def _work_title(div) -> str:
    title = fold_ligatures(smart_title_case((div.get("title") or "").strip()).rstrip(" ."))
    return _SPELLING.get(title, title)


# ------------------------------------------------------------------ paragraph selection

def recension_blocks(unit) -> tuple[list, list]:
    """A recension unit's (shorter, longer) paragraphs."""
    blocks = [b for b in direct_blocks(unit) if _block_text(b)]
    which = _RECENSION_OVERRIDE.get(unit.get("id"))
    if which == "short":
        return blocks, []
    if which == "long":
        return [], blocks
    if len(blocks) != 2:
        raise ValueError(f"recension unit {unit.get('id')} has {len(blocks)} paragraphs")
    return blocks[:1], blocks[1:]


def _commentator(block) -> bool:
    lead = next(iter(block), None)
    return (lead is not None and lead.tag == "span" and lead.get("class") == "sc"
            and (lead.text or "").strip() in _COMMENTATORS)


def commentary_blocks(canon) -> tuple[list, list]:
    """A canon's (Peter's, the commentators') paragraphs: the commentary starts at the
    first paragraph led by "Balsamon" or "Zonaras" in small capitals. The editor's
    heading over the canons, at the top of the first, is Peter's neither (rule G)."""
    blocks = direct_blocks(canon)
    at = next((k for k, b in enumerate(blocks) if _commentator(b)), len(blocks))
    own = [b for b in blocks[:at] if not _block_text(b).startswith(_CANONS_HEADING)]
    return own, blocks[at:]


def canons_heading(canon) -> list:
    return [b for b in direct_blocks(canon) if _block_text(b).startswith(_CANONS_HEADING)]


class _FathersEditor(Editor):
    """Rule G (1.8a), and, in the works that need it, only the paragraphs that are the
    work's own text (1.8c): the shorter Ignatian recension, Peter's canons without their
    commentators."""

    def __init__(self, source_file, source_key, parent_map, keep=None):
        super().__init__(source_file, source_key, parent_map)
        self.keep = keep

    def chapter(self, elem, label):
        edit = super().chapter(elem, label)
        if self.keep is None:
            return edit
        kept = {id(b) for b in self.keep(elem)}
        inner = edit.edit

        def own_only(block, marked, notes):
            if id(block) not in kept:
                return "", []
            return inner(block, marked, notes)

        edit.edit = own_only
        return edit


# ------------------------------------------------------------------ chapters

def _opening(filename, work):
    """The work div's own paragraphs above its first chapter, as an opening unit: a
    letter's greeting ("Salutation") or an address ("Opening"). None when the div holds
    none or only title lines. The caller asks only for a work with chapters: a work whose
    text is all in its own div is a whole work (1.8e)."""
    if (filename, work.get("id")) in _ROOT_TEXT_LATER:
        return None
    blocks = direct_blocks(work)
    if not blocks:
        return None
    if (filename, work.get("id")) in _RECENSIONS:
        blocks = recension_blocks(work)[0]
    text = strip_editorial_lines([t for b in blocks if (t := _block_text(b))],
                                 titles=(work.get("title") or "",))
    if not text:
        return None
    kind = "salutation" if _SALUTATION.match(text[0][:200]) else "opening"
    return (None, work, ChapterPlan(label=kind.title(), anchor=f"{work.get('id')}/{kind}",
                                    any_length=True))


def _heading_label(text: str) -> str:
    """"i. the exordium" -> "I. The Exordium"; "iv" -> "IV"."""
    m = re.match(r"^([ivxlc]+)\b\.?\s*(.*)$", text, re.IGNORECASE)
    if not m:
        return smart_title_case(text.upper())
    rest = smart_title_case(m.group(2).upper()) if m.group(2) else ""
    return f"{m.group(1).upper()}. {rest}" if rest else m.group(1).upper()


def _sections(work, parent_map) -> list:
    """A whole work's direct paragraphs cut at its headings, each run under a heading as
    a chapter div `<work id>/<numeral or slug>` titled by the heading."""
    from identity import slugify

    out = []
    current = None
    for child in work:
        if not isinstance(child.tag, str):
            continue
        if child.tag in _HEADINGS:
            text = " ".join(_strip_tags(tostring(child, encoding="unicode")).split())
            text = text.rstrip(".").strip()
            m = re.match(r"^([ivxlc]+)\b", text, re.IGNORECASE)
            name = m.group(1).lower() if m else slugify(text)[:40]
            current = Element("div3", {"id": f"{work.get('id')}/{name}", "title": text})
            parent_map[current] = work
            out.append(current)
        elif child.tag in ("p", "verse") and current is not None:
            current.append(child)
    return out


def _work_of(elem, root, level: int, parent_map):
    """The div at `level` under `root` that holds `elem` (itself included), or None."""
    cur = elem
    while cur is not None and cur is not root:
        if cur.tag == f"div{level}":
            return cur
        cur = parent_map.get(cur)
    return None


def _container_work(div, ordinal: int) -> Work:
    key = div.get("id")
    sender = _LETTER_SENDERS.get(key)
    if sender:
        return Work(work_key=key, ordinal=ordinal, title=f"{sender[0]}, to {sender[1]}",
                    author=sender[0])
    if key.startswith("iv.iv.") and div.get("shorttitle"):      # one of Cyprian's letters
        return Work(work_key=key, ordinal=ordinal, title=smart_title_case(div.get("shorttitle")))
    return Work(work_key=key, ordinal=ordinal,
                title=_WORK_TITLE_FIX.get(key) or _work_title(div))


def _anf_chapters(filename, work, parent_map, editor):
    """(chapters with their plans, works) for one ANF work div."""
    key = (filename, work.get("id"))
    if key in _WHOLE_WORK_DIVS:
        sections = [s for s in _sections(work, parent_map) if not editor.skip(s)]
        return [(None, s, ChapterPlan(label=_heading_label(s.get("title"))))
                for s in sections], []
    chapters = []
    works: dict[str, Work] = {}
    level = _CONTAINERS.get(key)
    embedded = _EMBEDDED_WORKS.get(key, {})
    for book, elem in iter_chapters(work, parent_map, editor.skip):
        parent = parent_map.get(elem)
        book = book or (_BOOK_FIX.get((filename, parent.get("id"))) if parent is not None
                        else None)
        plan = ChapterPlan()
        if key in _RECENSIONS:
            plan = ChapterPlan(anchor=f"{elem.get('id')}/short")
        elif level:
            w = _work_of(elem, work, level, parent_map)
            if w is not None:
                if w.get("id") not in works:
                    works[w.get("id")] = _container_work(w, len(works) + 1)
                # A chapter that is the work, or carries its name, needs no prefix.
                prefix = _WORK_TITLE_FIX.get(w.get("id")) or _chapter_label(w)
                if w is elem or _chapter_label(elem).casefold() == prefix.casefold():
                    prefix = None
                plan = ChapterPlan(work_key=w.get("id"), work_label=prefix)
        else:
            holder = next((k for k in embedded if elem.get("id", "").startswith(k + ".")),
                          None)
            if holder:
                title, prefix = embedded[holder]
                if holder not in works:
                    works[holder] = Work(work_key=holder, ordinal=len(works) + 1,
                                         title=title)
                label = re.sub(r"^(?:The )?Preface$", "Preface",
                               re.sub(r"^Chap\. ", "Chapter ", _chapter_label(elem)))
                plan = ChapterPlan(label=label, work_key=holder, work_label=prefix)
        chapters.append((book, elem, plan))
    opening = _opening(filename, work) if chapters else None
    if opening:
        chapters.insert(0, opening)
    return chapters, list(works.values())


def _keeper(key):
    if key in _RECENSIONS:
        return lambda unit: recension_blocks(unit)[0]
    if key in _COMMENTARY:
        return lambda canon: commentary_blocks(canon)[0]
    return None


def _anf_document(filename, father, work, parent_map, d1):
    """One ANF work's document, or None when it is an editor's or holds no text."""
    key = (filename, work.get("id"))
    editor = _FathersEditor(filename, _source_key(filename, work), parent_map,
                            keep=_keeper(key))
    if editor.skip(work):
        return None
    fix = _AUTHOR_FIX.get((filename, d1.get("id")))
    author = fix(work) if callable(fix) else fix or father
    title = _TITLE_FIX.get(key) or _work_title(work) or father
    if key in _RECENSIONS:
        title = title.removesuffix(_RECENSION_SUFFIX)
    chapters, works = _anf_chapters(filename, work, parent_map, editor)
    return _make_doc(filename, author, title, chapters, work=work, editor=editor,
                     works=works)


def build_documents(path: str) -> list[Document]:
    filename = os.path.basename(path)
    if filename == "summa.xml":
        return []
    root = _read_root(path)
    parent_map = _build_parent_map(root)
    docs: list[Document] = []

    single = _SINGLE_AUTHOR.get(filename)
    if single:
        title = smart_title_case((root.findtext(".//DC.Title") or "Unknown").strip())
        chapters = list(iter_chapters(root, parent_map))
        d = _make_doc(filename, single, title, chapters)
        if d:
            docs.append(d)
        return docs

    div1s = [d for d in root.iter("div1") if not _cf_skippable(d.get("title") or "")]
    if filename in _AUGUSTINE_FILES:
        # div1 = work; author is always Augustine.
        for d1 in div1s:
            title = smart_title_case((d1.get("title") or "").strip())
            d = _make_doc(filename, "Augustine", title, list(iter_chapters(d1, parent_map)),
                          work=d1)
            if d:
                docs.append(d)
    else:
        # Multi-author volume: div1 = father, div2 = work (else father itself is the work).
        # These are the ANF volumes, where rule G takes the editors' matter out (1.8a).
        for d1 in div1s:
            father = smart_title_case((d1.get("title") or "").strip())
            editor = Editor(filename, _source_key(filename, d1), parent_map)
            if editor.skip(d1):
                continue
            works = [w for w in d1.iter("div2") if not _cf_skippable(w.get("title") or "")]
            for w in works or [d1]:
                d = _anf_document(filename, father, w, parent_map, d1)
                if d:
                    docs.append(d)
    return docs


def build_all() -> list[Document]:
    docs: list[Document] = []
    for path in sorted(glob(os.path.join(_SRC_DIR, "*.xml"))):
        if path.endswith(".Zone.Identifier"):
            continue
        docs.extend(build_documents(path))
    return distinct_titles(docs)
