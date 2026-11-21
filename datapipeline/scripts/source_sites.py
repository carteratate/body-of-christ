"""The Sources page's data (corpus cleanup 4.4), generated from the rights inventory.

    cd datapipeline
    python3 scripts/source_sites.py [--check]

Where the digital text came from ("Sourced via CCEL.org", "Public domain. Sourced via
eBible.org", "Text: papalencyclicals.net") is not on the result card (4.4, rule 4): it is
on each document's overview and on About › Sources (`/about/sources`), which reads the
JSON this writes. One entry per site the published corpus takes text from: what is taken,
on what basis (each row's `status`, and its rights holder), and the documents. A row
planned for later (`planned_for`) or held by an open `document` removal (the papal
documents awaiting permission, ADR 0001) is not published and is not listed. An
edition a row names under `also_from` (an extract printed elsewhere) lists the document
under that edition's site too.

Rerun it after any change to `rights_inventory.json` or the removals; it is idempotent.
`--check` writes nothing and exits 1 when the JSON differs from what it would write.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import registry  # noqa: E402

INVENTORY = os.path.join(DATAPIPELINE, "rights_inventory.json")
OUTPUT = os.path.join(os.path.dirname(DATAPIPELINE), "apps", "web", "src", "lib",
                      "source-sites.json")

# Each site, in the order the page lists them: its name, its address, and what the corpus
# takes from it. `hosts` are the inventory's source_url hosts it covers.
SITES = (
    {"key": "ccel", "hosts": ("ccel.org", "www.ccel.org"),
     "name": "Christian Classics Ethereal Library (CCEL)", "url": "https://www.ccel.org",
     "taken": "English translations in CCEL's digital editions: the Church Fathers, the "
              "Summa Theologiae, medieval writers and the canons of the early councils."},
    {"key": "vatican", "hosts": ("www.vatican.va", "vatican.va"),
     "name": "The Holy See (vatican.va)", "url": "https://www.vatican.va",
     "taken": "The Holy See's English texts of papal documents, the Second Vatican Council "
              "and the Code of Canon Law.",
     "in_copyright": "In copyright, held by Libreria Editrice Vaticana. Its notice is shown "
                     "with every passage."},
    {"key": "usccb", "hosts": (),
     "name": "United States Conference of Catholic Bishops (USCCB)",
     "url": "https://www.usccb.org/beliefs-and-teachings/what-we-believe/catechism",
     "taken": "Excerpts of the Catechism of the Catholic Church, in its English "
              "translation for use in the United States.",
     "in_copyright": "In copyright, held by Libreria Editrice Vaticana and, for the English "
                     "translation, the USCCB. Its notice is shown with every passage, and "
                     "the full text is read on the USCCB's site."},
    {"key": "ebible", "hosts": ("ebible.org",),
     "name": "eBible.org", "url": "https://ebible.org",
     "taken": "The World English Bible, Catholic Edition."},
    {"key": "archive", "hosts": ("archive.org",),
     "name": "Internet Archive", "url": "https://archive.org",
     "taken": "Scans of printed translations, read from the page images. A passage taken "
              "from one is marked “scanned”."},
    {"key": "papalencyclicals", "hosts": ("www.papalencyclicals.net", "papalencyclicals.net"),
     "name": "Papal Encyclicals Online (papalencyclicals.net)",
     "url": "https://www.papalencyclicals.net",
     "taken": "Transcriptions of older printed translations."},
    {"key": "wikisource", "hosts": ("en.wikisource.org",),
     "name": "Wikisource", "url": "https://en.wikisource.org",
     "taken": "A transcription of an older printed translation."},
)

# The Catechism of the Catholic Church is credited to the USCCB, whose notice it carries,
# whatever file the structure is read from.
USCCB_WORKS = ("Catechism of the Catholic Church",)

BASIS = {
    "pd-us-pre-1931": "Public domain in the United States: published before 1931.",
    "pd-us-non-renewal": "Public domain in the United States: its copyright was not renewed.",
    "pd-dedicated": "Dedicated to the public domain.",
}


def _host(url: str | None) -> str | None:
    return urlparse(url).hostname if url else None


def _site_key(host: str | None) -> str | None:
    return next((s["key"] for s in SITES if host in s["hosts"]), None)


def _basis(key: str, row: dict) -> str:
    """The basis of one row: its public-domain status, or the site's in-copyright line.
    Any other status stops the build, so the page never states a basis nobody wrote."""
    if row["status"] in BASIS:
        return BASIS[row["status"]]
    site = next(s for s in SITES if s["key"] == key)
    if row["status"] == "in-copyright" and site.get("in_copyright"):
        return site["in_copyright"]
    raise ValueError(f"{row.get('work') or row.get('texts')}: no Sources page basis for "
                     f"status {row['status']!r} on {site['name']}")


def build(rows: list[dict], held: set[str]) -> dict:
    """The page's data from the inventory rows, without the held documents' rows."""
    sites: dict[str, dict] = {s["key"]: {"basis": {}, "documents": {}} for s in SITES}
    unknown: set[str] = set()

    def add(key, row, edition_row, texts=None):
        entry = sites[key]
        basis = _basis(key, edition_row)
        entry["basis"][basis] = entry["basis"].get(basis, 0) + 1
        doc = entry["documents"].setdefault(row["document_id"], {
            "document_id": row["document_id"], "title": row["work"],
            "collection": row["collection"], "texts": None})
        if texts:
            doc["texts"] = texts

    for row in rows:
        if row.get("planned_for") or not row.get("document_id") or row["document_id"] in held:
            continue
        key = "usccb" if row["work"] in USCCB_WORKS else _site_key(_host(row["source_url"]))
        if key is None:
            unknown.add(_host(row["source_url"]) or "(no source_url)")
        else:
            add(key, row, row)
        for edition in row.get("also_from") or ():
            extra = _site_key(_host(edition.get("source_url")))
            if extra is None:
                unknown.add(_host(edition.get("source_url")) or "(no source_url)")
            elif extra != key:
                add(extra, row, edition, edition.get("texts"))
    if unknown:
        raise ValueError(f"no Sources page entry for: {', '.join(sorted(unknown))}; add "
                         "one to SITES in scripts/source_sites.py")

    out = []
    for site in SITES:
        built = sites[site["key"]]
        if not built["documents"]:
            continue
        documents = sorted(built["documents"].values(),
                           key=lambda d: (d["collection"], d["title"].casefold()))
        out.append({
            "key": site["key"], "name": site["name"], "url": site["url"],
            "taken": site["taken"],
            "basis": sorted(built["basis"], key=lambda b: -built["basis"][b]),
            "documents": [{k: v for k, v in d.items() if v is not None} for d in documents],
        })
    return {"_generated_by": "datapipeline/scripts/source_sites.py", "sites": out}


def render() -> str:
    with open(INVENTORY, encoding="utf-8") as f:
        rows = json.load(f)
    data = build(rows, registry.removed_document_ids())
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="write nothing; exit 1 when the JSON is out of date")
    args = parser.parse_args(argv)
    text = render()
    try:
        with open(OUTPUT, encoding="utf-8") as f:
            current = f.read()
    except FileNotFoundError:
        current = None
    if args.check:
        if current != text:
            print(f"{OUTPUT} is out of date; run python3 scripts/source_sites.py")
            return 1
        return 0
    if current != text:
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(text)
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
