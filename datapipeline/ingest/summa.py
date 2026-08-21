"""Summa Theologica ingestion → one Document, one passage per article part.

SOURCE NOTE (leader-dot artifact): the NPNF source XML flattened a 3-column
comparison table into runs of ". . . . ." leader dots in a few articles (the
text before reads "may be seen from the following diagram"). These long runs
are collapsed by normalize.text.normalize_ellipses(). The cryptic reference
apparatus (Q[7], AA[3], FP/TP, QQ[1]-114, [*Cf. ...], "Question. N") is expanded
by normalize.summa.expand_apparatus() and shouting titles by title_case_shouting.

Structure: Part (div1) → Treatise (div2) → Question (div3) → Article (div4).
Each article splits into its dialectical parts (Objection N / On the contrary /
I answer that / Reply to Objection N), each a clean sub-passage of the article's
reader chapter; oversized parts are further split at sentence boundaries.
"""
from __future__ import annotations

import os
import re

import defusedxml.ElementTree as ET

from config import settings
from identity import document_id, anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from normalize.summa import expand_apparatus
from ingest.common import _extract_p_text, split_at_sentences, _split_at_whitespace

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "summa", "summa.xml")

# Splits an article body into its dialectical parts.
#
# The sed contra and respondeo appear in two punctuations. The comma'd form is matched
# anywhere (unchanged — it is what produced every existing split). The comma-less form
# is matched ONLY at a line start, because it is otherwise ambiguous with ordinary
# prose: exactly one article contains the cross-reference "(Arg. On the contrary)."
# inside its respondeo, and an unanchored comma-less alternative would split that
# article in two at a parenthetical citation.
#
# Measured against the live corpus 2026-08-20, where a surviving marker in a chunk's
# text proves the split missed it (a successful match consumes the marker into
# unit_label): 12 respondeo markers and 21 sed contra markers survive, every one of
# them comma-less and at a line start. Those 33 are what this recovers. The respondeo
# misses are the costly ones — they leave 16 articles with no "I answer that" chunk at
# all, so Aquinas's determination is absorbed into the preceding sed contra piece and
# the article looks, to search, like it has no answer.
#
# ⚠️ NOT YET APPLIED TO THE CORPUS. This runs at ingest; the live data was built by the
# previous pattern and still has those 33 misses. Re-ingesting solely to fix them is a
# bad trade — `run_collection.py` clears the collection first, and `retrievals`,
# `bookmarks`, `retrieval_labels` and `guest_trial_retrievals` all cascade on
# `chunks.id`. Let this ride along with the next Summa re-chunk. Until then, callers
# must tolerate an article with no respondeo chunk rather than assume one exists.
_PART_RE = re.compile(
    r"("
    r"Objection\s+\d+:"
    r"|Reply to Objection\s+\d+:"
    r"|On the contrary,"
    r"|I answer that,"
    r"|(?<=\n)On the contrary"
    r"|(?<=\n)I answer that"
    r")",
)


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", f.read(), flags=re.DOTALL)
    return ET.fromstring(xml)


def _cap_pieces(text: str, maxc: int) -> list[str]:
    """Split text so no piece exceeds the char budget (sentence-first, then hard
    whitespace split for any over-long remainder)."""
    pieces = split_at_sentences(text, target=maxc, overlap=0) if len(text) > maxc else [text]
    out: list[str] = []
    for p in pieces:
        out.extend(_split_at_whitespace(p, maxc, 0) if len(p) > maxc else [p])
    return out


def _split_article(text: str) -> list[tuple[str | None, str]]:
    """Return [(part_label, part_text)] split on the dialectical markers."""
    pieces = _PART_RE.split(text)
    if len(pieces) == 1:
        return [(None, text.strip())]
    out: list[tuple[str | None, str]] = []
    if pieces[0].strip():
        out.append((None, pieces[0].strip()))
    # pieces alternate: [pre, marker, body, marker, body, ...]
    for i in range(1, len(pieces), 2):
        marker = pieces[i].strip().rstrip(":,")
        body = pieces[i + 1].strip() if i + 1 < len(pieces) else ""
        out.append((marker, body))
    return out


def build_document(path: str | None = None) -> Document:
    root = _read_root(path or _SRC)
    maxc = settings.MAX_PASSAGE_CHARS
    passages: list[Passage] = []
    pos = 0
    for div1 in root.iter("div1"):
        part = expand_apparatus(title_case_shouting((div1.get("title") or "").strip()))
        for div3 in div1.iter("div3"):        # Question
            q = expand_apparatus(title_case_shouting((div3.get("title") or "").strip()))
            for div4 in div3.iter("div4"):    # Article
                a_title = expand_apparatus(title_case_shouting((div4.get("title") or "").strip()))
                body = clean_text(expand_apparatus(_extract_p_text(div4)))
                if len(body) < 50:
                    continue
                ch_key = make_anchor("summa", part, q, a_title)
                ch_label = f"{q} — {a_title}".strip(" —")
                ref = f"Summa Theologiae, {part}, {q}, {a_title}"
                sub = 0
                for label, ptext in _split_article(body):
                    for piece in _cap_pieces(ptext, maxc):
                        passages.append(Passage(
                            content=piece, reference=ref,
                            anchor=f"{ch_key}/{sub}", chapter_key=ch_key,
                            chapter_label=ch_label, position=pos,
                            unit_label=label, metadata={"part": part}))
                        pos += 1
                        sub += 1
    return Document(id=document_id("summa"), collection="summa",
                    title="Summa Theologiae", author="Thomas Aquinas",
                    metadata={"source_file": "summa.xml"}, passages=passages)
