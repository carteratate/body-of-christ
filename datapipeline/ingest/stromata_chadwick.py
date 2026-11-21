"""Clement's *Stromata* Book III in Henry Chadwick's English (#399).

ANF left all of Book III ("On Marriage") in Latin, and 3.3 retired its 33 passages under
rule E. Chadwick's translation, in J. E. L. Oulton and H. Chadwick, *Alexandrian
Christianity* (Library of Christian Classics II, 1954), pp. 40–92, is public domain in
the United States (Carter, 16 Nov 2026), so the passages come back in his English with
their IDs (Carter, 21 Nov 2026: the whole book, chapters 1 to 18).

The text comes through the OCR tool from the scan's text layer, frozen in
`ocr/texts/chadwick-stromata-3.json`, one passage per Stählin section (`ch03/s012`; a
long one in parts, `-01`, `-02`). Chadwick numbers by Stählin's sections, ANF's Latin
by nothing finer than the book, and its passages were cut by length. `PIECES` aligns
them: each ANF passage, by its anchor, opens in Chadwick at the section and words that
translate its first Latin sentence, and runs to the next one's opening. Where a Latin
passage opens inside a sentence (`from-p27-2`, `from-p67`), the English passage opens at
the next sentence, or at the start of that sentence, so no sentence is cut.

Chadwick's notes, his section numbers and chapter headings never reach the text; the
scripture references ANF's Latin notes gave go with the Latin. Each passage carries the
translator's note (`NOTE`; Carter, 21 Nov 2026) and `text_replaced`, since its text is
replaced on purpose and keeps its ID.
"""
from __future__ import annotations

import re
from dataclasses import replace

from model import Document
from ocr.fixes import read_text

WORK = "chadwick-stromata-3"
SCAN_URL = "https://archive.org/details/alexandrianchris012826mbp"
STROMATA = "3a68ef3f-b829-5e95-9eeb-f1ef299c4a38"
SOURCE_FILE = "second-century.xml"   # ANF vol. 2, where Book III is the div `BOOK`
BOOK = "vi.iv.iii"
NOTE = "In Henry Chadwick's translation (1954)."
TEXT_REPLACED = "Chadwick (1954) replaces ANF's Latin"

# (ANF anchor, Stählin section, the words its English opens with), in order. The
# section's own opening where the Latin passage opens with it.
PIECES: tuple[tuple[str, int, str], ...] = (
    (BOOK, 1, "The Valentinians, who hold"),
    (f"{BOOK}/from-p9", 5, "But the followers of Carpocrates"),
    (f"{BOOK}/from-p9-2", 8, "The saying in the law"),
    (f"{BOOK}/from-p17", 12, "If Plato himself"),
    (f"{BOOK}/from-p27", 16, "As scattered leaves"),
    # The Latin opens inside the sentence that asks whether Heraclitus calls birth death.
    (f"{BOOK}/from-p27-2", 21, "What then? Does not Heraclitus"),
    (f"{BOOK}/from-p36", 25, "Of the heretics we mentioned"),
    (f"{BOOK}/from-p36-2", 28, "Moreover, the apostle teaches us"),
    (f"{BOOK}/from-p36-3", 34, "Because of this certain other"),
    (f"{BOOK}/from-p36-4", 37, "Do you not perceive"),
    (f"{BOOK}/from-p63", 40, "It is not our aim"),
    # The Latin opens inside the sentence ending "now and hereafter".
    (f"{BOOK}/from-p67", 42, "If, then, all things were lawful"),
    (f"{BOOK}/from-p72", 45, "To those, on the other hand"),
    (f"{BOOK}/from-p81", 48, "If, as they say"),
    (f"{BOOK}/from-p81-2", 52, "And Samuel the prophet"),
    (f"{BOOK}/from-p102", 54, "How can there be one who asks"),
    (f"{BOOK}/from-p117", 57, "The human ideal of continence"),
    (f"{BOOK}/from-p124", 61, "Those who hold that for them"),
    (f"{BOOK}/from-p131", 63, "Those who are opposed to God"),
    (f"{BOOK}/from-p131-2", 67, "But I am aware that"),
    (f"{BOOK}/from-p143", 71, "The demonstration of these matters"),
    (f"{BOOK}/from-p143-2", 76, "In the Epistle to the Romans"),
    (f"{BOOK}/from-p162", 79, "If by agreement"),
    (f"{BOOK}/from-p162-2", 82, "The point of the apostle"),
    (f"{BOOK}/from-p162-3", 85, "And no doubt of such people"),
    (f"{BOOK}/from-p162-4", 88, "But just as “the unmarried woman"),
    (f"{BOOK}/from-p199", 91, "Such are the arguments"),
    (f"{BOOK}/from-p202", 94, "He then does violence"),
    (f"{BOOK}/from-p209", 96, "And again when the apostle"),
    (f"{BOOK}/from-p225", 100, "When Jeremiah says"),
    (f"{BOOK}/from-p236", 102, "If birth is something evil"),
    (f"{BOOK}/from-p246", 105, "Some, then, as we have shown"),
    (f"{BOOK}/from-p246-2", 108, "What reply to these directions"),
)

_UNIT = re.compile(r"^ch(\d{2})/s(\d{3})(?:-\d{2})?$")


def sections(frozen: dict | None = None) -> dict[int, str]:
    """Each Stählin section's text, its parts joined, by number."""
    frozen = frozen or read_text(WORK)
    out: dict[int, str] = {}
    for unit in frozen["passages"]:
        m = _UNIT.match(unit["id"])
        if m is None:
            raise ValueError(f"{WORK}: unit {unit['id']!r} names no section")
        n = int(m.group(2))
        sep = "" if n not in out else " " if unit.get("continues") else "\n\n"
        out[n] = out.get(n, "") + sep + unit["text"]
    return out


def english(frozen: dict | None = None) -> dict[str, str]:
    """Each ANF anchor's English text, by `PIECES`. Raises when an opening is not found
    in its section, or the pieces leave out or repeat any of the text."""
    by_section = sections(frozen)
    numbers = sorted(by_section)
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError(f"{WORK}: sections are not 1 to {len(numbers)}")
    # Every section joined, each opening a paragraph; each piece's start in that text.
    starts, text, at = {}, "", {}
    for n in numbers:
        at[n] = len(text) + (2 if text else 0)
        text += ("\n\n" if text else "") + by_section[n]
    for anchor, section, opening in PIECES:
        body = by_section[section]
        k = _find(body, opening)
        if k is None:
            raise ValueError(f"{anchor}: section {section} does not hold {opening!r}")
        starts[anchor] = at[section] + k
    order = [a for a, _, _ in PIECES]
    if starts[order[0]] != 0 or [starts[a] for a in order] != sorted(starts[a] for a in order):
        raise ValueError(f"{WORK}: the pieces do not open the text in order")
    out = {}
    for i, anchor in enumerate(order):
        end = starts[order[i + 1]] if i + 1 < len(order) else len(text)
        out[anchor] = text[starts[anchor]:end].strip()
    return out


def _find(body: str, opening: str) -> int | None:
    """Where `opening` starts in `body`, read with straight and curly quotation marks
    alike, at the start of a sentence (the section's start, or after a stop)."""
    def fold(s: str) -> str:
        return s.translate(str.maketrans("“”‘’", "\"\"''"))
    folded, want = fold(body), fold(opening)
    for m in re.finditer(re.escape(want), folded):
        k = m.start()
        while k and folded[k - 1] in "\"'":
            k -= 1
        if k == 0 or re.search(r"[.?!:\"')…]\s+$", folded[max(0, k - 4):k]):
            return k
    return None


def restore(document: Document, frozen: dict | None = None) -> Document:
    """The Stromata with Book III's passages in Chadwick's English, keeping their
    anchors (and so their IDs), chapter and order. Each built passage of `BOOK` must be
    one `PIECES` names."""
    if document.id != STROMATA:
        return document
    texts = english(frozen)
    meta = (frozen or read_text(WORK))["metadata"]
    book = [p for p in document.passages if p.anchor.split("/")[0] == BOOK]
    if [p.anchor for p in book] != list(texts):
        raise ValueError(f"{document.title}: Book III's passages are not {WORK}'s pieces: "
                         f"{[p.anchor for p in book]}")
    passages = []
    for p in document.passages:
        if p.anchor in texts:
            kept = {k: v for k, v in (p.metadata or {}).items()
                    if k in ("source_file", "book")}
            # The Latin unit the piece opens with still names where it starts; offsets
            # into the Latin mean nothing in the English.
            p = replace(p, content=texts[p.anchor], source_units=p.source_units[:1] and (
                            (p.source_units[0][0], 0),), note=NOTE,
                        metadata={**kept, "url": SCAN_URL, "text_replaced": TEXT_REPLACED,
                                  **meta})
        passages.append(p)
    return replace(document, passages=passages)
