"""The Catechism of the Council of Trent, McHugh and Callan's translation (New York:
Wagner, 1923), corpus-cleanup 5.5.

Read from 1.2f's frozen OCR text, `ocr/texts/mchugh-callan-roman-catechism.json`, which
the work's config (`ocr/works/mchugh-callan-roman-catechism.json`) cleans from the 1923
printing's Internet Archive scan, `catechismofcounc0000jose`, pp. 1–590. Its units
(`ocr.units.RomanCatechism`) are the translators' sections: the headings they set over each
section, then its text. Fordham's transcription was used only to check the OCR (Carter,
5 Oct 2026), never as the text.

The Catechism printed no headings of its own, so every heading is McHugh and Callan's
(rule G): a section's heading becomes its passage's unit label and the chapters are the
book's Parts, Articles, Sacraments, Commandments and Petitions (`CHAPTERS`), never
passage text. Their introduction, sermon programme, notes and appendices are left out
(rule G): the config reads only pp. 1–590, and the clean-up keeps the notes apart.

A passage is one section, cut at paragraphs where it runs past `MAX_CHARS`. Every
passage carries the scanned-text label (`ocr.label`).
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from identity import PIECE_MARK, anchor as make_anchor  # noqa: E402
from ingest.catechism import _title  # noqa: E402
from ingest.common import split_display_passage  # noqa: E402
from ingest.pieces import piece_reference  # noqa: E402
from model import Document, Passage  # noqa: E402
from normalize.text import clean_text  # noqa: E402
from ocr.fixes import read_text  # noqa: E402
from ocr.label import label_passage  # noqa: E402
from ocr.units import roman_catechism_heading  # noqa: E402
from registry import ANCHOR_SCHEME, resolve_document_id  # noqa: E402

WORK = "mchugh-callan-roman-catechism"
SCAN = "catechismofcounc0000jose"
SOURCE_KEY = "catechism/roman-catechism"
TITLE = "Catechism of the Council of Trent"
YEAR = 1566
NOTE = ("Catechism of the Council of Trent, a historical catechism; for current teaching see "
        "the Catechism of the Catholic Church")
MAX_CHARS = 3500


@dataclass(frozen=True)
class Chapter:
    key: str             # anchor path under the document
    label: str           # the reader's chapter label
    short: str           # what a reference names
    page: int            # the printed page it opens on
    opens: str           # a heading of its first section, as the OCR reads it


# The translators' chapters, in order, each found at the first section on or after its
# page whose headings match `opens`. A chapter title that opens a page is lost with the
# running heads ("ARTICLE V", "THE FIRST PETITION OF THE LORD'S PRAYER"), so `opens`
# is then the first heading the page keeps; pages checked against the scan.
def _articles() -> list[Chapter]:
    titles = [
        (14, "I", "“I Believe in God, the Father Almighty, Creator of Heaven and Earth”",
         r"^ARTICLE I$"),
        (31, "II", "“And in Jesus Christ, His Only Son, Our Lord”", r"^ARTICLE II$"),
        (41, "III", "“Who was Conceived by the Holy Ghost, Born of the Virgin Mary”",
         r"^ARTICLE III$"),
        (50, "IV", "“Suffered under Pontius Pilate, was Crucified, Dead, and Buried”",
         r"^ARTICLE IV$"),
        (62, "V", "“He Descended into Hell, the Third Day He Rose Again from the Dead”",
         r"FROM THE DEAD”$"),
        (73, "VI", "“He Ascended into Heaven, Sitteth at the Right Hand of God the Father "
         "Almighty”", r"^ARTICLE VI$"),
        (80, "VII", "“From Thence He Shall Come to Judge the Living and the Dead”",
         r"THE DEAD”$"),
        (88, "VIII", "“I Believe in the Holy Ghost”", r"^ARTICLE VIII$"),
        (96, "IX", "“I Believe in the Holy Catholic Church; the Communion of Saints”",
         r"^ARTICLE IX$"),
        (113, "X", "“The Forgiveness of Sins”", r"^ARTICLE X$"),
        (120, "XI", "“The Resurrection of the Body”", r"^ARTICLE XI$"),
        (132, "XII", "“Life Everlasting”", r"(?i)^“\S+ EVERLASTING”$"),
    ]
    return [Chapter(f"creed/article-{k}", f"Part I, The Creed, Article {n}, {t}",
                    f"Creed, Article {n}", page, opens)
            for k, (page, n, t, opens) in enumerate(titles, 1)]


_SACRAMENTS = [("baptism", "Baptism", 161), ("confirmation", "Confirmation", 199),
               ("eucharist", "the Eucharist", 213), ("penance", "Penance", 261),
               ("extreme-unction", "Extreme Unction", 307),
               ("holy-orders", "Holy Orders", 317), ("matrimony", "Matrimony", 338)]
_ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth"]

CHAPTERS: list[Chapter] = [
    Chapter("introductory", "Introductory", "Introductory", 1, r"^INTRODUCTORY$"),
    Chapter("creed", "Part I, The Creed", "Creed", 9, r"^PART I$"),
    *_articles(),
    Chapter("sacraments", "Part II, The Sacraments", "Sacraments", 141, r"^PART II$"),
    *[Chapter(f"sacraments/{k}", f"Part II, The Sacraments, The Sacrament of {name}",
              f"Sacraments, {name[:1].upper()}{name[1:]}", page,
              rf"^THE SACRAMENT OF {name.upper()}$") for k, name, page in _SACRAMENTS],
    Chapter("decalogue", "Part III, The Decalogue", "Decalogue", 357, r"^PART III$"),
    *[Chapter(f"decalogue/commandment-{k}",
              f"Part III, The Decalogue, The {word} Commandment",
              f"Decalogue, {word} Commandment", page, opens)
      for k, (word, page, opens) in enumerate([
          ("First", 366, r"^THE FIRST COMMANDMENT$"),
          ("Second", 382, r"^THE SECOND COMMANDMENT$"),
          ("Third", 396, r"^THE THIRD COMMANDMENT$"),
          ("Fourth", 408, r"^THE FOURTH COMMANDMENT$"),
          ("Fifth", 420, r"^THE FIFTH COMMANDMENT$"),
          ("Sixth", 431, r"^THE POSITION OF THIS COMMANDMENT"),
          ("Seventh", 440, r"^THE SEVENTH COMMANDMENT$"),
          ("Eighth", 454, r"^THE EIGHTH COMMANDMENT$")], 1)],
    Chapter("decalogue/commandments-9-10",
            "Part III, The Decalogue, The Ninth and Tenth Commandments",
            "Decalogue, Ninth and Tenth Commandments", 466,
            r"^THE NINTH AND TENTH COMMANDMENTS$"),
    Chapter("lords-prayer", "Part IV, The Lord’s Prayer", "Lord’s Prayer", 477, r"^PART IV$"),
    Chapter("lords-prayer/opening-words",
            "Part IV, The Lord’s Prayer, Opening Words: “Our Father who art in heaven”",
            "Lord’s Prayer, Opening Words", 500, r"^OPENING WORDS OF THE LORD’S PRAYER$"),
    *[Chapter(f"lords-prayer/petition-{k}",
              f"Part IV, The Lord’s Prayer, The {_ORDINALS[k - 1]} Petition: {words}",
              f"Lord’s Prayer, {_ORDINALS[k - 1]} Petition", page, opens)
      for k, (words, page, opens) in enumerate([
          ("“Hallowed be thy name”", 513, r"^WHY THIS PETITION IS PLACED FIRST$"),
          ("“Thy kingdom come”", 519, r"^IMPORTANCE OF INSTRUCTION ON THIS PETITION$"),
          ("“Thy will be done”", 528,
           r"^THE THIRD PETITION OF THE LORD’S PRAYER$"),
          ("“Give us this day our daily bread”", 540,
           r"^THE RELATION OF THE FOLLOWING PETITIONS"),
          ("“And forgive us our debts, as we forgive our debtors”", 552, r"^THE IMPORTANCE OF EXPLAINING THIS PETITION$"),
          ("“And lead us not into temptation”", 564, r"^THE SIXTH PETITION"),
          ("“But deliver us from evil”", 577,
           r"^THE IMPORTANCE OF INSTRUCTION ON THIS PETITION$")], 1)],
    Chapter("lords-prayer/amen", "Part IV, The Lord’s Prayer, The Seal of the Lord’s Prayer: "
            "“Amen”", "Lord’s Prayer, Amen", 585,
            r"^NECESSITY OF EXPLAINING THE CONCLUSION"),
]

# Headings that name a Part or a chapter, never a section's label.
_STRUCTURAL = re.compile(
    r"^(?:PART [IV]+|ARTICLE [IVXL]+|INTRODUCTORY|THE (?:CREED|SACRAMENTS|DECALOGUE)"
    r"|THE LORD’S PRAYER|THE SACRAMENT OF [A-Z ]+|THE [A-Z]+ COMMANDMENTS?"
    r"|THE NINTH AND TENTH COMMANDMENTS|THE [A-Z]+ PETITION OF THE LORD’S PRAYER"
    r"|OPENING WORDS OF THE LORD’S PRAYER)$")


@dataclass
class _Section:
    unit: str
    headings: list[str]
    # The printed pages of the OCR passages the section's text is read from: a passage
    # holds several sections, so this can name a page or two around the section's own.
    paragraphs: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)


def _sections(passages: list[dict]) -> list[_Section]:
    """The translators' sections, read off the passages' paragraphs in order: a run of
    headings opens one, and the text up to the next heading is its own. A passage can
    end inside a section, and one marked `continues` opens inside a paragraph; `unit`
    names the passage the section opens in."""
    out: list[_Section] = []
    for p in passages:
        for k, para in enumerate(q for q in p["text"].split("\n\n") if q.strip()):
            if k == 0 and p.get("continues"):
                # The paragraph runs on from the passage before (a page-foot note cut it).
                if not out or not out[-1].paragraphs:
                    raise ValueError(f"roman catechism: {p['id']} continues no paragraph")
                out[-1].paragraphs[-1] += " " + para
            elif roman_catechism_heading(para):
                if not out or out[-1].paragraphs:
                    out.append(_Section(p["id"], []))
                out[-1].headings.append(para)
            else:
                if not out:
                    raise ValueError(f"roman catechism: text before the first heading in {p['id']}")
                out[-1].paragraphs.append(para)
            for pg in p["pages"]:
                if pg and pg not in out[-1].pages:
                    out[-1].pages.append(pg)
    if out and not out[-1].paragraphs:
        raise ValueError("roman catechism: the text ends with a heading")
    return out


def _chapter_starts(sections: list[_Section]) -> list[int]:
    """The index of each chapter's first section."""
    starts, k = [], 0
    for chapter in CHAPTERS:
        rx = re.compile(chapter.opens)
        k = next((i for i in range(k, len(sections))
                  if sections[i].pages and int(sections[i].pages[-1]) >= chapter.page
                  and any(rx.search(h) for h in sections[i].headings)), None)
        if k is None:
            raise ValueError(f"roman catechism: no section opens {chapter.key} "
                             f"({chapter.opens!r} from p. {chapter.page})")
        starts.append(k)
    if starts[0] != 0:
        raise ValueError("roman catechism: text before the Introductory")
    return starts


def label(headings: list[str]) -> str | None:
    """A section's label: its last heading that is not a Part's or a chapter's, in title
    case where the print sets it in capitals ("ADVANTAGES OF CONFESSION")."""
    own = [h for h in headings if not _STRUCTURAL.match(h.strip(" .:"))]
    if not own:
        return None
    text = own[-1].strip(" .")
    return _title(text) if text.upper() == text else text


def _pieces(paragraphs: list[str]) -> list[tuple[int, str]]:
    """(first paragraph, text) of each piece: paragraphs packed up to `MAX_CHARS`, and a
    longer paragraph cut on its own."""
    out: list[tuple[int, str]] = []
    current: list[str] = []
    first = 0
    for i, para in enumerate(paragraphs):
        if current and len("\n\n".join(current + [para])) > MAX_CHARS:
            out.append((first, "\n\n".join(current)))
            current = []
        if not current:
            first = i
        current.append(para)
    if current:
        out.append((first, "\n\n".join(current)))
    pieces: list[tuple[int, str]] = []
    for first, text in out:
        pieces += [(first, t) for t in split_display_passage(text, MAX_CHARS)]
    return pieces


def build_document(text: dict | None = None) -> Document:
    data = text if text is not None else read_text(WORK)
    sections = _sections(data["passages"])
    starts = _chapter_starts(sections)
    did = resolve_document_id("catechism", SOURCE_KEY, ("catechism", "roman-catechism"))
    passages: list[Passage] = []
    for c, chapter in enumerate(CHAPTERS):
        end = starts[c + 1] if c + 1 < len(CHAPTERS) else len(sections)
        for n, section in enumerate(sections[starts[c]:end], 1):
            unit_label = label(section.headings)
            base = make_anchor(*chapter.key.split("/"), n)
            pieces = _pieces(section.paragraphs)
            seen: dict[int, int] = {}
            for k, (first, body) in enumerate(pieces, 1):
                seen[first] = seen.get(first, 0) + 1
                anchor = base if k == 1 else (
                    f"{base}{PIECE_MARK}p{first + 1}"
                    + (f"-{seen[first]}" if seen[first] > 1 else ""))
                ref = f"Roman Catechism, {chapter.short}" + (f", {unit_label}" if unit_label else "")
                passage = Passage(
                    content=clean_text(body),
                    reference=piece_reference(ref, None, None, k, len(pieces)),
                    anchor=anchor, chapter_key=make_anchor("roman-catechism", *chapter.key.split("/")),
                    chapter_label=chapter.label, position=len(passages), unit_label=unit_label,
                    metadata={"pages": section.pages, "ocr_unit": section.unit})
                passages.append(label_passage(passage, data["metadata"]["scan_id"]))
    return Document(
        id=did, collection="catechism", title=TITLE, author=None, year=YEAR,
        notes=NOTE,
        metadata={"source": "McHugh and Callan, Catechism of the Council of Trent for Parish "
                            "Priests (1923), Internet Archive scan, through the OCR tool (1.2f)",
                  "source_key": SOURCE_KEY, "source_file": f"{SCAN}/",
                  "url": f"https://archive.org/details/{SCAN}",
                  "anchor_scheme": ANCHOR_SCHEME},
        passages=passages)
