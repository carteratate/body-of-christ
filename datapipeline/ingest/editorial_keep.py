"""Augustine's own words that the NPNF editors quote inside their own matter (1.8b).

Rule G takes the translators' prefaces and the editor's introductory notices out of the
NPNF Augustine volumes, but where they quote Augustine, the quotation is his text and
stays: his Retractations on each work, and the letter to Aurelius he asked to have set
before On the Trinity (Carter, 12 Nov 2026). Each row is read from the source by hand,
since where a quotation begins and ends is too irregular to find by pattern: it names the
editor's div, the first and last paragraph the quotation spans, and the words it begins
and ends with, which cut the editor's lead-in ("From the Retractations, ii. 21.", "In the
Retractations (ii. 15) Augustin speaks of this work in the following terms:—") and the
quotation marks around it.

Each row becomes a passage of the work the div belongs to, in the div's place, labelled
by `label`, anchored `<div>/<slug>`, with metadata `{"from": source, "quoted_in": …}`.
`checks.source_text` reads the same rows, so the coverage checks count the quotation as
body text and the rest of the div as apparatus.
"""
from __future__ import annotations

import re
from typing import NamedTuple


class KeptQuote(NamedTuple):
    file: str
    div: str        # the editor's div that prints it
    first: str      # the first paragraph it spans
    last: str       # the last paragraph it spans
    start: str      # the words it begins with, in `first`
    end: str        # the words it ends with, in `last` (kept)
    label: str      # its chapter label
    source: str     # where Augustine wrote it, as metadata["from"]
    slug: str = "retractations"

    @property
    def anchor(self) -> str:
        return f"{self.div}/{self.slug}"


KEPT_QUOTES: tuple[KeptQuote, ...] = (
    # On the Holy Trinity, translator's preface.
    KeptQuote("on-the-holy-trinity.xml", "iv.i.ii", "iv.i.ii-p10", "iv.i.ii-p10",
              "I spent some years", "love of my brethren had forced me to do.",
              "Retractations II.15", "Retractations"),
    KeptQuote("on-the-holy-trinity.xml", "iv.i.ii", "iv.i.ii-p12", "iv.i.ii-p13",
              "To the most blessed Lord", "Farewell. Pray for me.",
              "Letter to Aurelius", "Epistle 174", slug="letter-to-aurelius"),
    # The Enchiridion, introductory notice.
    KeptQuote("on-the-holy-trinity.xml", "iv.ii.i", "iv.ii.i-p4", "iv.ii.i-p4",
              "I also wrote a book on Faith", "The book begins: ‘I cannot express,’",
              "Retractations II.63", "Retractations"),
    # On the Catechising of the Uninstructed, introductory notice.
    KeptQuote("on-the-holy-trinity.xml", "iv.iii.i", "iv.iii.i-p2", "iv.iii.i-p2",
              "There is also a book of ours", "‘You have requested me, brother Deogratias.’",
              "Retractations II.14", "Retractations"),
    # A Treatise on Faith and the Creed, introductory notice.
    KeptQuote("on-the-holy-trinity.xml", "iv.iv.i", "iv.iv.i-p5", "iv.iv.i-p5",
              "About the same period", "commences thus: ‘Since it is written,’",
              "Retractations I.17", "Retractations"),
    # On the Profit of Believing, translator's preface.
    KeptQuote("on-the-holy-trinity.xml", "iv.vi.i", "iv.vi.i-p1", "iv.vi.i-p1",
              "Moreover now at Hippo-Regius", "unum atque idem videretur esse.”",
              "Retractations I.14", "Retractations"),
    # Of Holy Virginity, translator's preface. The quotation's last words, "This book
    # begins,", introduce an opening the translator left out ("&c."), so they go with it.
    KeptQuote("on-the-holy-trinity.xml", "v.iii.i", "v.iii.i-p1", "v.iii.i-p1",
              "After I had written", "so far as I was able I set forth in one volume.",
              "Retractations II.23", "Retractations"),
    # On Lying, translator's preface ("Retractations, Book I. last Chapter.").
    KeptQuote("on-the-holy-trinity.xml", "v.v.i", "v.v.i-p3", "v.v.i-p3",
              "I have also written a Book on Lying", "“Magna quæstio est de Mendacio.”",
              "Retractations I.27", "Retractations"),
    # Against Lying, translator's preface.
    KeptQuote("on-the-holy-trinity.xml", "v.vi.i", "v.vi.i-p2", "v.vi.i-p2",
              "Then also I wrote a Book against Lying", "It begins: Multa mihi legenda misisti.",
              "Retractations II.60", "Retractations"),
    # Of the Work of Monks, translator's preface.
    KeptQuote("on-the-holy-trinity.xml", "v.vii.i", "v.vii.i-p2", "v.vii.i-p2",
              "To write the Book on the Work of Monks", "“Jussioni tuæ, sancte frater Aureli.”",
              "Retractations II.21", "Retractations"),
    # On Care to Be Had for the Dead, translator's preface.
    KeptQuote("on-the-holy-trinity.xml", "v.ix.i", "v.ix.i-p2", "v.ix.i-p2",
              "The book, On care to be had for the dead", "my venerable fellow-bishop Paulinus.",
              "Retractations II.64", "Retractations"),
    # On Christian Doctrine, the editor's introductory note.
    KeptQuote("city-of-god.xml", "v.i", "v.i-p4", "v.i-p4",
              "Finding that the books on Christian Doctrine", "‘On Sacraments or Philosophy.’",
              "Retractations II.4", "Retractations"),
    # City of God, translator's preface: "the account given by Augustin himself".
    KeptQuote("city-of-god.xml", "iv.i", "iv.i-p3", "iv.i-p5",
              "Rome having been stormed", "and called them The City of God.",
              "Retractations II.43", "Retractations"),
)


def kept_quotes(file: str) -> list[KeptQuote]:
    return [q for q in KEPT_QUOTES if q.file == file]


def quoted_text(text: str, quote: KeptQuote, block_id: str) -> tuple[int, int] | None:
    """The span of a paragraph's `text` the quotation holds: from `start` in its first
    paragraph, to the end of `end` in its last, and in a paragraph after the first
    without the opening quotation mark a quotation printed over several paragraphs
    repeats. None when the paragraph is not one it spans. A ValueError names a row whose
    words the paragraph does not hold."""
    if block_id == quote.first:
        a = _find(text, quote.start, quote, block_id).start()
    else:
        a = len(text) - len(text.lstrip(" \n“"))
    b = len(text)
    if block_id == quote.last:
        b = _find(text, quote.end, quote, block_id).end()
    return a, b


def _find(text: str, words: str, quote: KeptQuote, block_id: str):
    """Where `words` stand in `text`, however the source breaks its lines."""
    m = re.search(r"\s+".join(map(re.escape, words.split())), text)
    if m is None:
        raise ValueError(f"{quote.anchor}: {block_id} does not hold {words!r}")
    return m


_MARK = "⁣"     # ingest.common._NOTE_MARK


class QuoteEdit:
    """The edit `ingest.thml_doc.make_doc` applies to a kept quotation's chapter: each
    paragraph cut to the span `quoted_text` gives, with the notes that stood inside it."""

    label_title = None

    def __init__(self, quote: KeptQuote):
        self.quote = quote

    def edit(self, block, marked: str, notes: list[str]) -> tuple[str, list[str]]:
        plain = marked.replace(_MARK, "")
        span = quoted_text(plain, self.quote, block.get("id"))
        if span is None:
            return "", []
        # Map the span on the plain text back onto the marked text.
        index = [k for k, c in enumerate(marked) if c != _MARK] + [len(marked)]
        a, b = index[span[0]], index[span[1]] if span[1] < len(plain) else len(marked)
        marks = [k for k, c in enumerate(marked) if c == _MARK]
        kept = [n for n, at in zip(notes, marks) if a <= at < b]
        return marked[a:b].strip(), kept
