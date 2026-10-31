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

Anchors come from the source's own ids, never from a part label or an article title
(2.1, Decision log "Summa anchors (2.1)"): a part is `summa/<article div id>/<paragraph>`,
named by the source paragraph it opens in (`FP_Q29_A2-p5` in `FP_Q29_A2` is `p5`), with
`-2` when a second part opens in the same paragraph. Its later pieces follow
`ingest.pieces`. The labels are wrong in dozens of places (C-04, C-14); 1.7 corrects
them without touching an anchor.
"""
from __future__ import annotations

import os
import re

from xml.etree.ElementTree import tostring as et_tostring  # serialization only

import defusedxml.ElementTree as ET

from config import settings
from identity import anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from normalize.summa import expand_apparatus
from ingest.common import _extract_p_text, _strip_tags, split_display_passage
from ingest.pieces import Segment, SourceMap, name_pieces
from registry import ANCHOR_SCHEME, resolve_document_id

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
# previous pattern and still has those 33 misses. Publishing solely to fix them is a
# deliberate corpus change: rebuilding the affected passage boundaries may trigger the
# identity-churn guard. Let this ride along with the next planned Summa re-chunk. Until
# then, callers must tolerate an article with no respondeo passage rather than assume
# one exists.
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


def _split_article(text: str) -> list[tuple[str | None, str]]:
    """Return [(part_label, part_text)] split on the dialectical markers."""
    return [(label, body) for label, body, _, _ in _article_parts(text)]


def _article_parts(text: str) -> list[tuple[str | None, str, int, int]]:
    """[(part_label, part_text, where the part opens, where its text starts)]: a part
    opens at its marker, or at its text when it has none."""
    marks = list(_PART_RE.finditer(text))
    if not marks:
        return [(None, text.strip(), 0, text.find(text.strip()))]
    out: list[tuple[str | None, str, int, int]] = []
    pre = text[:marks[0].start()].strip()
    if pre:
        start = text.find(pre)
        out.append((None, pre, start, start))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end].strip()
        start = text.find(body, m.end()) if body else m.end()
        out.append((m.group(0).strip().rstrip(":,"), body, m.start(), start))
    return out


def paragraph_segments(div) -> list[Segment]:
    """The article's paragraphs, as `_extract_p_text` reads them, each named by its source
    id without the article's id in front (`FP_Q29_A2-p5` in `FP_Q29_A2` is `p5`)."""
    article = div.get("id") or ""
    out = []
    for k, p in enumerate(div.iter("p"), 1):
        text = _strip_tags(et_tostring(p, encoding="unicode", method="xml"))
        if not text:
            continue
        pid = p.get("id") or f"n{k}"
        if article and pid.startswith(article + "-"):
            pid = pid[len(article) + 1:]
        out.append(Segment(pid, text))
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
                article = div4.get("id")
                if not article:
                    raise ValueError(f"summa: article {a_title!r} has no div id to anchor on")
                segments = paragraph_segments(div4)
                source = SourceMap(body, segments)
                opened: dict[int, int] = {}      # paragraph -> parts anchored in it
                for label, ptext, opens_at, text_at in _article_parts(body):
                    pieces = split_display_passage(ptext, maxc)
                    if not pieces:
                        continue
                    s, _ = source.segment_at(opens_at)
                    opened[s] = opened.get(s, 0) + 1
                    unit = f"summa/{article}/{segments[s].locator}" + \
                        (f"-{opened[s]}" if opened[s] > 1 else "")
                    for piece, (anchor, units) in zip(pieces, name_pieces(
                            unit, ptext, pieces, segments, source, offset=text_at)):
                        passages.append(Passage(
                            content=piece, reference=ref, anchor=anchor,
                            chapter_key=ch_key, chapter_label=ch_label, position=pos,
                            unit_label=label, metadata={"part": part},
                            source_units=units))
                        pos += 1
    return Document(id=resolve_document_id("summa", "summa", ("summa",)), collection="summa",
                    title="Summa Theologiae", author="Thomas Aquinas",
                    metadata={"source_file": "summa.xml", "source_key": "summa",
                              "anchor_scheme": ANCHOR_SCHEME},
                    passages=passages)
