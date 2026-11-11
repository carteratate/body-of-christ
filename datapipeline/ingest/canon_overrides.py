"""Canon law: the current text the vatican.va English Code lacks (corpus-cleanup 1.5b, R2).

Two kinds of canon are changed after the pages are parsed:

- English overrides. The De concordia inter Codices canons (2016) take the L'Osservatore
  Romano English of 23 Sep 2016, p. 9, labelled unofficial, with a link to the official
  Latin. The text lives in the vendored `sources/canon-law/overrides.json`, which
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
    "title": "Apostolic Letter issued Motu Proprio De concordia inter Codices",
    "url": "https://www.vatican.va/content/francesco/la/apost_letters/documents/"
           "papa-francesco-lettera-ap_20160531_de-concordia-inter-codices.html",
}
EWTN_URL = "https://www.ewtn.com/catholicism/library/de-concordia-inter-codices-7264"
EWTN_TITLE = ("De concordia inter Codices, L'Osservatore Romano, Weekly Edition in English, "
              "23 September 2016, page 9 (EWTN Library reprint)")

# De concordia's articles that this item takes, by number: (canon, field, change). Art. 4
# and 5 (868 §1 2° and §3) wait for the print check of 868 §3 (NEEDS-CARTER, section C).
ARTICLES = {
    1: (111, "content", "replace"),
    2: (112, "content", "replace"),
    3: (535, "§2", "replace"),
    6: (1108, "§3", "add"),
    7: (1109, "content", "replace"),
    8: (1111, "§1", "replace"),
    9: (1112, "§1", "replace"),
    10: (1116, "§3", "add"),
    11: (1127, "§1", "replace"),
}


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
    868: NoEnglish(2016, DE_CONCORDIA["url"]),
}


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

    def index_row(self) -> dict[str, str]:
        return {"canon": str(self.canon), "field": self.field, "change": self.change,
                "status": self.status, "language": self.language,
                "source_title": self.source_title, "source_url": self.source_url,
                "retrieved": self.retrieved, "page_sha256": self.page_sha256,
                "text_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
                "official_latin_url": self.official_latin_url}


INDEX_FIELDS = ("canon", "field", "change", "status", "language", "source_title",
                "source_url", "retrieved", "page_sha256", "text_sha256",
                "official_latin_url")


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
    overrides = [Override(**r) for r in rows]
    for o in overrides:
        if o.status not in STATUSES or o.change not in CHANGES:
            raise ValueError(f"canon {o.canon}: status {o.status!r}, change {o.change!r}")
        if o.canon in NO_ENGLISH:
            raise ValueError(f"canon {o.canon} has no English and takes no override")
        if o.field != "content" and not re.fullmatch(r"§\d+", o.field):
            raise ValueError(f"canon {o.canon}: field {o.field!r}")
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
        n = int(o.field[1:])
        groups = _paragraphs(content)
        numbers = [g[0] for g in groups]
        if o.change == "replace":
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
        if field != "content" and not text.startswith(field + "."):
            raise ValueError(f"article {art}: expected {field}, found {text[:20]!r}")
        out.append(Override(canon=canon, field=field, change=change, text=text,
                            language="en", status=UNOFFICIAL_ENGLISH,
                            source_title=EWTN_TITLE, source_url=EWTN_URL, retrieved=retrieved,
                            page_sha256=sha, official_latin_url=DE_CONCORDIA["url"]))
    return out


def write(overrides: list[Override], path: str = OVERRIDES, index: str = INDEX) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"overrides": [o.__dict__ for o in overrides]}, f, ensure_ascii=False,
                  indent=1)
        f.write("\n")
    with open(index, "w", encoding="utf-8") as f:
        f.write(index_csv(overrides))
