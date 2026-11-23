"""Shared ThML per-work Document builder.

Extracted from church_fathers so medieval (also CCEL ThML) reuses one tested
path. Builds a Document of clean Passages from a flat list of
(book_label|None, chapter_element) pairs, flattening book->chapter into labels.

Anchors come from the source's structure (2.1): a chapter's anchor and chapter key are
its div's `id`, exactly as the file writes it, and a later split piece is named by the
first paragraph it holds (`ingest.pieces`). Labels never reach an anchor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from xml.etree.ElementTree import tostring as et_tostring  # serialization only

import headings
from config import settings
from model import Document, Passage, Work
from normalize.text import clean_text, fold_ligatures
from normalize.caps import roman_capitals, smart_title_case
from ingest.common import _block_text, _book_label, direct_blocks_text, direct_text_with_notes
from ingest.pieces import Segment, name_pieces, pack_units, piece_reference, piece_spans
from ingest.scripture_notes import scripture_reference
from registry import ANCHOR_SCHEME, resolve_document_id


@dataclass(frozen=True)
class ChapterPlan:
    """What an adapter decides about one chapter beyond what its div says (1.8c). A
    chapter given to `make_doc` as `(book, elem, plan)` takes these; `(book, elem)` takes
    none."""
    label: str | None = None        # the chapter's own label, in place of the div's
    anchor: str | None = None       # the unit's anchor, in place of the div id
    work_key: str | None = None     # the work of a container document it belongs to (D6)
    work_label: str | None = None   # set before the book in the label, as a book is
    cites: str | None = None        # the title its reference cites in place of the
                                    # document's: a work inside another (C-15)
    any_length: bool = False        # kept however short (a letter's greeting)
    meta: dict | None = None        # added to its passages' metadata (1.8b's quotations)
    # Paragraphs that are the work's own headings, by `<p>` id: (id, level, whether it
    # repeats the chapter label). Each stays in the text, is marked (`headings.py`,
    # #445) and is kept in one piece with what follows it.
    headings: tuple[tuple[str, int, bool], ...] = ()
    # Headings the work prints before the chapter, outside its div (a book's or part's
    # own title over its first chapter): (text, level). Each opens the chapter's text,
    # marked, in the order given.
    lead: tuple[tuple[str, int], ...] = ()


# The Panegyric's chapters carry the editor's "Argument I" as their short title (1.8c).
_ARGUMENT_SHORTTITLE = re.compile(r"^Argument ([IVXLC]+)$")
# A label taken from a long title keeps the whole title up to this length, and past it is
# cut at the last word boundary before it (1.9; Bernard's titles run to about 125).
LABEL_MAX_CHARS = 140


def _clip(head: str) -> str:
    if len(head) <= LABEL_MAX_CHARS:
        return head
    cut = head[:LABEL_MAX_CHARS + 1].rsplit(None, 1)[0]
    return cut.rstrip(" ,;:.—-")


def _chapter_label(elem) -> str:
    """A short, clean chapter heading from ThML shorttitle/title/n attributes."""
    st = (elem.get("shorttitle") or "").strip()
    title = (elem.get("title") or "").strip()
    n = (elem.get("n") or "").strip()
    typ = (elem.get("type") or "").strip().lower()
    if m := _ARGUMENT_SHORTTITLE.match(st):
        return f"Chapter {m.group(1)}"
    if st and not st.endswith("...") and len(st) <= 45:
        return smart_title_case(st)
    if typ == "chapter" and n:
        return f"Chapter {n}"
    head = re.split(r"\.?—|—", title)[0].strip().rstrip(".")
    if head:
        return smart_title_case(_clip(head))
    return f"Chapter {n}" if n else "Section"


def paragraph_segments(elem, edit=None) -> list[Segment]:
    """The div's direct paragraphs and verse blocks, as `_direct_p_text` reads them, each
    named by its `id` without the div's own id in front (`ii.iii-p5` in div `ii.iii` is
    `p5`, a verse block `ii.iii-p5.1` is `p5.1`), or, with no id, `n<k>`: its ordinal
    among the div's `<p>` and `<verse>` children. `edit` is `direct_blocks_text`'s."""
    div = elem.get("id") or ""
    out, k = [], 0
    for child in elem:
        if child.tag not in ("p", "verse"):
            continue
        k += 1
        text = _block_text(child)
        if edit is not None and text:
            text = edit(child, text, [])[0]
        if not text:
            continue
        pid = child.get("id")
        if pid and div and pid.startswith(div + "-"):
            pid = pid[len(div) + 1:]
        out.append(Segment(pid or f"n{k}", text))
    return out


def notes_per_piece(raw: str, parts: list[str], notes: list[tuple[int, str]]
                    ) -> list[list[tuple[int, str]]]:
    """The removed notes that stood in each piece cut from `raw`, as (offset in the
    piece, note text) (1.10b)."""
    starts = piece_spans(raw, parts)
    out: list[list[tuple[int, str]]] = [[] for _ in parts]
    k = 0
    for at, text in sorted(notes, key=lambda n: n[0]):
        while k + 1 < len(starts) and at >= starts[k + 1]:
            k += 1
        out[k].append((at - starts[k], text))
    return out


def footnotes(part: str, content: str, notes: list[tuple[int, str]]) -> list[dict]:
    """The scripture references among a piece's removed notes, as the Catechism stores
    its footnotes (#279): `{n, text, at}`, numbered from 1 in the piece, `at` the
    offset in the cleaned `content` just after the word the note followed."""
    out = []
    for at, text in notes:
        ref = scripture_reference(text)
        if ref is None:
            continue
        x = min(len(clean_text(part[:at]).rstrip()), len(content))
        out.append({"n": len(out) + 1, "text": ref, "at": x})
    return out


def _label(text: str) -> str:
    return fold_ligatures(text.strip().rstrip(" ."))


def _locator(pid: str, div: str) -> str:
    """A paragraph's id as `paragraph_segments` names it: without its div's id in front."""
    return pid[len(div) + 1:] if div and pid.startswith(div + "-") else pid


def _heading_marks(raw: str, segments: list[Segment], headings_wanted: list,
                   filename: str) -> list[dict]:
    """(locator, level, repeats the label) as marks on `raw`, whose paragraphs are
    `segments` in order."""
    blocks = raw.split("\n\n")
    if len(blocks) != len(segments):
        raise ValueError(f"{filename}: {len(blocks)} paragraphs read, {len(segments)} named")
    wanted = {locator: (level, repeats) for locator, level, repeats in headings_wanted}
    out, at = [], 0
    for block, segment in zip(blocks, segments):
        if segment.locator in wanted:
            level, repeats = wanted.pop(segment.locator)
            lead = len(block) - len(block.lstrip())
            out.append(headings.mark(at + lead, at + lead + len(block.strip()),
                                     level=level, chapter_title=repeats))
        at += len(block) + 2
    if wanted:
        raise ValueError(f"{filename}: headings {sorted(wanted)} are not paragraphs read")
    return out


def _marks_in_content(part: str, content: str, marks: list[dict], filename: str,
                      anchor: str) -> list[dict]:
    """A piece's marks, offsets into `part`, moved to the same paragraphs of `content`
    (`clean_text` changes lengths, never the paragraphs)."""
    before, after = headings.paragraphs(part), headings.paragraphs(content)
    if len(before) != len(after):
        raise ValueError(f"{filename}: {anchor}: cleaning changed its paragraphs")
    index = {span: k for k, span in enumerate(before)}
    return [{**m, "at": after[index[(m["at"], m["end"])]][0],
             "end": after[index[(m["at"], m["end"])]][1]} for m in marks]


def _reference(title: str, label: str) -> str:
    """A chapter's citation: no author (C-15). The card, the copied citation and the
    models take the author from the resolved display author, so a relabel reaches them."""
    return f"{title}, {label}"


def make_doc(*, collection: str, filename: str, author: str, title: str,
             chapters: list, source_key: str, year: int | None = None,
             extra_meta: dict | None = None, editor=None,
             works: list[Work] | None = None) -> Document | None:
    """Build one Document from (book|None, chapter_elem) pairs, or (book, elem,
    `ChapterPlan`) triples. Returns None if empty.
    `source_key` names the work in the source (file, plus the work div's id when the
    file holds several works); the registry freezes the document ID under it.
    `editor` (`ingest.editorial.Editor`), when given, takes the editors' lines and
    brackets out of each chapter (rule G, 1.8a). `works` are the works of a container
    document (D6), which its chapters' plans name by `work_key`."""
    if not chapters:
        return None
    # ANF and NPNF headings end in a period ("Methodius.", "Fragments."), and some spell
    # ligatures ("Irenæus"). Neither belongs in a label. The registry keeps the document
    # ID, and `identity.slugify` drops the punctuation anyway (1.10a).
    author, title = _label(author), _label(title)
    maxc = settings.MAX_PASSAGE_CHARS
    passages: list[Passage] = []
    pos = 0
    elems = {id(c[1]) for c in chapters}
    parents = {id(c[1]) for c in chapters
               if any(a is not c[1] and id(a) in elems for a in c[1].iter())}
    for book, elem, *rest in chapters:
        plan = rest[0] if rest else ChapterPlan()
        if len(direct_text_with_notes(elem)) < 100 and not plan.any_length:
            continue
        self_book = _book_label(elem)
        if plan.label:
            core = plan.label
        elif book is None and self_book:
            # A book's own text above its chapters is its introduction; a book with no
            # chapters of its own (Boethius's five) is labelled by its name alone (1.9).
            book = self_book
            core = "Introduction" if id(elem) in parents else None
        else:
            core = _chapter_label(elem)
        chapter = editor.chapter(elem, core or book) if editor is not None else None
        edit = chapter.edit if chapter is not None else None
        raw, removed = direct_blocks_text(elem, edit)
        if not raw:
            continue
        if chapter is not None and chapter.label_title:
            core = chapter.label_title
        core = roman_capitals(fold_ligatures(core)) if core else None
        book_clean = roman_capitals(fold_ligatures(smart_title_case(book))) if book else None
        label = " · ".join(x for x in (plan.work_label, book_clean, core) if x)
        ch_key = elem.get("id")
        if not ch_key:
            raise ValueError(f"{filename}: chapter {label!r} has no div id to anchor on")
        meta = {"source_file": filename}
        if book_clean:
            meta["book"] = book_clean
        if extra_meta:
            meta.update(extra_meta)
        if plan.meta:
            meta.update(plan.meta)
        segments = paragraph_segments(elem, edit)
        wanted = [(_locator(pid, ch_key), level, repeats)
                  for pid, level, repeats in plan.headings]
        if plan.lead:
            prefix = "\n\n".join(text for text, _ in plan.lead)
            raw = f"{prefix}\n\n{raw}"
            removed = [(at + len(prefix) + 2, text) for at, text in removed]
            leads = [Segment(f"lead-{k}", text) for k, (text, _) in enumerate(plan.lead, 1)]
            segments = leads + segments
            wanted = [(s.locator, level, False)
                      for s, (_, level) in zip(leads, plan.lead)] + wanted
        # Pieces hold whole paragraphs and verse blocks (1.10c); `raw` joins them so.
        parts = [p.text for p in pack_units([(None, b) for b in raw.split("\n\n")], maxc)]
        marks = _heading_marks(raw, segments, wanted, filename) if wanted else []
        if marks:
            parts = headings.hold_headings(raw, parts, marks)
        piece_marks = headings.split_marks(raw, parts, marks) if marks else [[]] * len(parts)
        named = name_pieces(plan.anchor or ch_key, raw, parts, segments)
        for k, (part, (anchor, units), notes, held) in enumerate(zip(
                parts, named, notes_per_piece(raw, parts, removed), piece_marks), 1):
            # Notes are editor material (rule G): their count is kept, and the scripture
            # references among them become the passage's footnotes.
            content = clean_text(part)
            piece_meta = meta
            if notes:
                piece_meta = {**meta, "editor_note_count": len(notes)}
                refs = footnotes(part, content, notes)
                if refs:
                    piece_meta["footnotes"] = refs
            if held:
                piece_meta = headings.with_headings(
                    piece_meta, _marks_in_content(part, content, held, filename, anchor))
            passages.append(Passage(
                content=content,
                reference=piece_reference(
                    _reference(plan.cites, " · ".join(x for x in (book_clean, core) if x))
                    if plan.cites else _reference(title, label), None, None,
                                          k, len(parts)),
                anchor=anchor, chapter_key=ch_key, chapter_label=label,
                position=pos, unit_label=None, metadata=piece_meta, source_units=units,
                work_key=plan.work_key))
            pos += 1
    if not passages:
        return None
    doc_meta = {"source_file": filename, "source_key": source_key,
                "anchor_scheme": ANCHOR_SCHEME}
    if extra_meta:
        doc_meta.update(extra_meta)
    did = resolve_document_id(collection, source_key, (collection, author, title))
    used = {p.work_key for p in passages}
    works = [replace(w, ordinal=k) for k, w in
             enumerate((w for w in works or [] if w.work_key in used), 1)]
    return Document(id=did, collection=collection,
                    title=title, author=author, year=year, metadata=doc_meta,
                    passages=passages, works=works)


def distinct_titles(documents: list[Document]) -> list[Document]:
    """No two documents of a collection share a title (C-15): where they do once their
    trailing periods are gone (Papias's "Fragments" and Methodius's "Fragments."), each
    takes its author: "Fragments of Papias", "Epistle of Polycarp to the Philippians".
    Their passages' references follow, piece suffixes kept. Document IDs come from the
    registry and stay."""
    by_title: dict[str, list[Document]] = {}
    for d in documents:
        by_title.setdefault(d.title.casefold(), []).append(d)
    for shared in by_title.values():
        if len(shared) < 2:
            continue
        for d in shared:
            old = d.title
            d.title = _with_author(d.title, d.author)
            for p in d.passages:
                if not p.reference.startswith(old):
                    raise ValueError(f"{d.id}: reference {p.reference!r} does not open "
                                     f"with its title")
                p.reference = d.title + p.reference[len(old):]
    return documents


def _with_author(title: str, author: str) -> str:
    head, sep, rest = title.partition(" ")
    if head in ("Epistle", "Letter") and rest.startswith("to "):
        return f"{head} of {author} {rest}"
    return f"{title} of {author}"
