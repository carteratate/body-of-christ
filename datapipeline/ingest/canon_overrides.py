"""Canon law: the current text the vatican.va English Code lacks (corpus-cleanup 1.5b, R2).

Two kinds of canon are changed after the pages are parsed:

- English overrides. The De concordia inter Codices canons (2016) take the L'Osservatore
  Romano English of 23 Sep 2016, p. 9, labelled unofficial, with a link to the official
  Latin. An override replaces the whole canon, one paragraph (`§2`) or one numbered item
  of a paragraph (`§1 2°`), or adds a paragraph. A typo the reprint prints is corrected
  only where `CORRECTIONS` declares it, and the override records it (#400). The text lives in the vendored `sources/canon-law/overrides.json`, which
  `scripts/vendor_sources.py --collection canon-law` builds from the EWTN reprint, so it
  stays out of the public repo like the pages. The tracked
  `canon_overrides_index.csv` lists every override without its text, with the text's
  sha256; a build refuses an override file that does not match it.
- Canons with no English (rule E as revised 29 Oct 2026). The adapter emits no passage
  for them, current or history; the removal registry retires each live passage with a
  tombstone, and the document's metadata maps each anchor to its Latin on vatican.va.

Decision log "Canon law English and amendments (R2)".
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

_DIR = os.path.dirname(os.path.dirname(__file__))
OVERRIDES = os.path.join(_DIR, "sources", "canon-law", "overrides.json")
INDEX = os.path.join(_DIR, "canon_overrides_index.csv")

UNOFFICIAL_ENGLISH = "unofficial_english"
STATUSES = ("official", UNOFFICIAL_ENGLISH)
CHANGES = ("replace", "add")

DE_CONCORDIA = {
    # As the canon pages title it (c. 111's amended_by).
    "title": ("Apostolic Letter issued 'Motu Proprio' “De concordia inter Codices” "
              "modifying some norms of the Code of Canon Law"),
    "url": "https://www.vatican.va/content/francesco/la/apost_letters/documents/"
           "papa-francesco-lettera-ap_20160531_de-concordia-inter-codices.html",
}
EWTN_URL = "https://www.ewtn.com/catholicism/library/de-concordia-inter-codices-7264"
EWTN_TITLE = ("De concordia inter Codices, L'Osservatore Romano, Weekly Edition in English, "
              "23 September 2016, page 9 (EWTN Library reprint)")

# De concordia's articles that this item takes, by number: (canon, field, change). Art. 4
# and 5 (868 §1 2° and §3) joined after the republish (#400): the printed page could not
# be reached, and Carter chose the reprint's text with one typo corrected (16 Nov 2026).
ARTICLES = {
    1: (111, "content", "replace"),
    2: (112, "content", "replace"),
    3: (535, "§2", "replace"),
    4: (868, "§1 2°", "replace"),
    5: (868, "§3", "add"),
    6: (1108, "§3", "add"),
    7: (1109, "content", "replace"),
    8: (1111, "§1", "replace"),
    9: (1112, "§1", "replace"),
    10: (1116, "§3", "add"),
    11: (1127, "§1", "replace"),
}
# The canons whose new text the page prints, in Latin, with the 1983 English as its
# earlier version (1.5a builds that history passage). The page prints the other De
# concordia canons in their 1983 English as if current, so the adapter keeps that English
# as their history passage.
PAGE_PRINTS_LATIN = frozenset({111, 112, 535, 868})
# The reprint's typos corrected, by article: (as printed, as published). Nothing else in an
# article's text is changed; each printed string must occur once.
CORRECTIONS = {
    5: (("for than", "for them"),),
}
# What a reader of the override file should know about an article's text.
NOTES = {
    4: ("Agrees word for word with the Canon Law Society of Great Britain and Ireland's "
        "English Code (R2), which stands in for the print check."),
    5: ("The reprint is the only L'Osservatore Romano witness: the printed page could not "
        "be reached, so this text is unchecked against it (Carter, 16 Nov 2026, #400). "
        "\"The actual ministry\" stays as the reprint prints it, although the Latin is "
        "ministrum proprium (\"their own minister\")."),
}
TEXT_REPLACED = {True: "unofficial English replaces Latin",
                 False: "2016 amendment, in unofficial English"}


@dataclass(frozen=True)
class NoEnglish:
    """A canon whose current text has no English: retired, with a link to its Latin."""
    year: int           # the year its current text was made
    latin_url: str      # where its current Latin is on vatican.va


_PRELATURES = ("https://www.vatican.va/content/francesco/it/motu_proprio/documents/"
               "20230808-motu-proprio-prelature-personali.html")
# R2; the act pages print each canon's current Latin. Expedit ut iura has no Latin page:
# its English page quotes the canon in Latin.
NO_ENGLISH = {
    295: NoEnglish(2023, _PRELATURES),
    296: NoEnglish(2023, _PRELATURES),
    579: NoEnglish(2020, "https://www.vatican.va/content/francesco/la/motu_proprio/documents/"
                         "papa-francesco-motu-proprio-20201101_authenticum-charismatis.html"),
    695: NoEnglish(2022, "https://www.vatican.va/content/francesco/la/motu_proprio/documents/"
                         "20220426-motu-proprio-recognitum-librum-vi.html"),
    700: NoEnglish(2023, "https://www.vatican.va/content/francesco/en/motu_proprio/documents/"
                         "20230402-motu-proprio-expedit-ut-iura.html"),
}


def latin_urls() -> dict[str, str]:
    """Each retired canon's anchor and its Latin on vatican.va: the Code's
    `metadata.official_latin_urls`, which the reader's notice links (2.4f)."""
    return {f"can/{n}": NO_ENGLISH[n].latin_url for n in sorted(NO_ENGLISH)}


def tombstone(canon: int) -> str:
    return (f"Canon {canon} was amended in {NO_ENGLISH[canon].year}; "
            "no English translation is available.")


def document_note() -> str:
    """The Code's document note naming the canons not shown, kept in step with NO_ENGLISH."""
    nums = [str(n) for n in sorted(NO_ENGLISH)]
    listed = f"{', '.join(nums[:-1])} and {nums[-1]}" if len(nums) > 1 else nums[0]
    return (f"Canons {listed} are not shown: their current text has no English "
            "translation. The official Latin is on vatican.va.")


# --------------------------------------------------------------------------- the file

@dataclass(frozen=True)
class Override:
    canon: int
    field: str          # "content", or a paragraph such as "§2"
    change: str         # replace, or add (a paragraph the canon did not have)
    text: str
    language: str
    status: str
    source_title: str
    source_url: str
    retrieved: str
    page_sha256: str
    official_latin_url: str
    # (as printed, as published) for each typo corrected in `text` (CORRECTIONS).
    corrections: tuple[tuple[str, str], ...] = ()
    notes: str = ""

    def index_row(self) -> dict[str, str]:
        return {"canon": str(self.canon), "field": self.field, "change": self.change,
                "status": self.status, "language": self.language,
                "source_title": self.source_title, "source_url": self.source_url,
                "retrieved": self.retrieved, "page_sha256": self.page_sha256,
                "text_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
                "official_latin_url": self.official_latin_url,
                "corrections": "; ".join(f"{a} -> {b}" for a, b in self.corrections),
                "notes": self.notes}


INDEX_FIELDS = ("canon", "field", "change", "status", "language", "source_title",
                "source_url", "retrieved", "page_sha256", "text_sha256",
                "official_latin_url", "corrections", "notes")
_FIELD = re.compile(r"^(?:content|§(\d+)(?: (\d+)°)?)$")


def index_csv(overrides: list[Override]) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=INDEX_FIELDS, lineterminator="\n")
    w.writeheader()
    for o in sorted(overrides, key=lambda o: (o.canon, o.field)):
        w.writerow(o.index_row())
    return out.getvalue()


def load(path: str = OVERRIDES, index: str = INDEX) -> dict[int, list[Override]]:
    """The overrides by canon. Raises when the file is missing, malformed, or differs from
    the tracked index (a text whose sha256 is not the one reviewed, a row either lacks)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path}: run scripts/vendor_sources.py --collection canon-law")
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)["overrides"]
    overrides = [Override(**{**r, "corrections": tuple(tuple(c) for c in
                                                     r.get("corrections", ()))})
                 for r in rows]
    for o in overrides:
        if o.status not in STATUSES or o.change not in CHANGES:
            raise ValueError(f"canon {o.canon}: status {o.status!r}, change {o.change!r}")
        if o.canon in NO_ENGLISH:
            raise ValueError(f"canon {o.canon} has no English and takes no override")
        m = _FIELD.match(o.field)
        if not m or (m.group(2) and o.change != "replace"):
            raise ValueError(f"canon {o.canon}: field {o.field!r}, change {o.change!r}")
    with open(index, encoding="utf-8") as f:
        tracked = f.read()
    if index_csv(overrides) != tracked:
        raise ValueError(f"{os.path.basename(path)} differs from {os.path.basename(index)}: "
                         "an override's text or source is not the one reviewed")
    by_canon: dict[int, list[Override]] = {}
    for o in overrides:
        by_canon.setdefault(o.canon, []).append(o)
    return by_canon


# --------------------------------------------------------------------------- applying

_PARA = re.compile(r"^§\s*(\d+)\.")


def _paragraphs(content: str) -> list[tuple[int | None, list[str]]]:
    """A canon's lines grouped by paragraph: (§ number or None, lines)."""
    groups: list[tuple[int | None, list[str]]] = []
    for line in content.split("\n"):
        m = _PARA.match(line)
        if m or not groups:
            groups.append((int(m.group(1)) if m else None, [line]))
        else:
            groups[-1][1].append(line)
    return groups


def apply(canon: int, content: str, overrides: list[Override]) -> str:
    """The canon's content with its overrides applied, in order."""
    for o in overrides:
        if o.field == "content":
            content = o.text
            continue
        para, item = _FIELD.match(o.field).groups()
        n = int(para)
        groups = _paragraphs(content)
        numbers = [g[0] for g in groups]
        if item is not None:
            if n not in numbers:
                raise ValueError(f"canon {canon}: no §{n} for {o.field}")
            groups[numbers.index(n)] = (n, _replace_item(canon, o, groups[numbers.index(n)][1],
                                                         int(item)))
        elif o.change == "replace":
            if n not in numbers:
                raise ValueError(f"canon {canon}: no {o.field} to replace")
            groups[numbers.index(n)] = (n, o.text.split("\n"))
        else:
            if n in numbers or n - 1 not in numbers:
                raise ValueError(f"canon {canon}: {o.field} cannot be added after "
                                 f"paragraphs {numbers}")
            groups.insert(numbers.index(n - 1) + 1, (n, o.text.split("\n")))
        content = "\n".join(line for _, lines in groups for line in lines)
    return content


_ITEM = re.compile(r"^((?:§\s*\d+\.\s*)?)(\d+)\s*([/°])\s*")


def _replace_item(canon: int, o: Override, lines: list[str], item: int) -> list[str]:
    """A paragraph's lines with numbered item `item` replaced by the override's text, which
    reads `§N. M° ...`. The line keeps the marker the page prints (`2/`), so the canon's
    items stay alike."""
    head = _prefix(o.field)
    if not o.text.startswith(head + " "):
        raise ValueError(f"canon {canon}: {o.field} text does not open with {head!r}")
    hits = [i for i, line in enumerate(lines)
            if (m := _ITEM.match(line)) and int(m.group(2)) == item]
    if len(hits) != 1:
        raise ValueError(f"canon {canon}: no single item {item}° in §{o.field[1:].split()[0]}")
    m = _ITEM.match(lines[hits[0]])
    new = f"{m.group(1)}{item}{m.group(3)} {o.text[len(head):].strip()}"
    return lines[:hits[0]] + [new] + lines[hits[0] + 1:]


def _prefix(field: str) -> str:
    """How the article's text opens for a field: `§2.` for `§2`, `§1. 2°` for `§1 2°`."""
    para, _, item = field.partition(" ")
    return f"{para}. {item}" if item else f"{para}."


# --------------------------------------------------------------------------- vendoring

_ARTICLE = re.compile(r"^Art\.\s*(\d+)\.")
_END = re.compile(r"^I decree that\b")


def extract_de_concordia(html: str) -> dict[int, str]:
    """The text each article of the EWTN reprint gives, by article number: the paragraphs
    after the article's heading line, one line each, up to the next article or the
    closing decree."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[int, list[str]] = {}
    article: int | None = None
    for p in soup.find_all("p"):
        text = re.sub(r"\s+", " ", p.get_text("")).strip()
        if not text:
            continue
        m = _ARTICLE.match(text)
        if m:
            article = int(m.group(1))
            if article in out:
                raise ValueError(f"article {article} appears twice")
            out[article] = []
        elif _END.match(text):
            article = None
        elif article is not None:
            out[article].append(text)
    if sorted(out) != list(range(1, 12)):
        raise ValueError(f"expected articles 1 to 11, found {sorted(out)}")
    return {n: "\n".join(lines) for n, lines in out.items()}


def build_overrides(html: bytes, retrieved: str) -> list[Override]:
    """The overrides file's rows from the fetched EWTN page."""
    sha = hashlib.sha256(html).hexdigest()
    texts = extract_de_concordia(html.decode("utf-8"))
    out = []
    for art, (canon, field, change) in sorted(ARTICLES.items()):
        text = texts[art]
        if field != "content" and not text.startswith(_prefix(field)):
            raise ValueError(f"article {art}: expected {field}, found {text[:20]!r}")
        for printed, corrected in CORRECTIONS.get(art, ()):
            if text.count(printed) != 1:
                raise ValueError(f"article {art}: {printed!r} occurs {text.count(printed)} "
                                 "times, not once")
            text = text.replace(printed, corrected)
        out.append(Override(canon=canon, field=field, change=change, text=text,
                            language="en", status=UNOFFICIAL_ENGLISH,
                            source_title=EWTN_TITLE, source_url=EWTN_URL, retrieved=retrieved,
                            page_sha256=sha, official_latin_url=DE_CONCORDIA["url"],
                            corrections=CORRECTIONS.get(art, ()),
                            notes=NOTES.get(art, "")))
    return out


def write(overrides: list[Override], path: str = OVERRIDES, index: str = INDEX) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"overrides": [o.__dict__ for o in overrides]}, f, ensure_ascii=False,
                  indent=1)
        f.write("\n")
    with open(index, "w", encoding="utf-8") as f:
        f.write(index_csv(overrides))
