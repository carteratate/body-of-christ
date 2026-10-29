"""Build the table of where each Catechism paragraph is printed in the USCCB flipbook.

Writes app/catechism_pages.json: for every paragraph §1–§2865, the flipbook page on which
it starts. The API links an excerpt Catechism passage to that page instead of the cover
(app/catechism_pages.py). The file holds page numbers only, no text.

The flipbook (FlippingBook Publisher, usccb.org) publishes no text or search index, only
one transparent PNG of text per page. This script downloads those images and the
viewer's index.html, pager.js and workspace.js (once, at one request a second, into a
cache directory outside the repo; usccb.org's bot check starts refusing requests after a
few hundred, so a rerun reuses the cache), reads the images with Tesseract,
and takes the bold paragraph numbers that open lines at the text column's left edge.
Margin cross-references sit left of the column, footnote numbers are indented, and the
running header is above the body, so position alone sets them apart. Every number found
must then agree with our text: the words printed after it must match the opening of that
paragraph in the vendored US edition (datapipeline/sources/catechism/us-edition/
ccc-us.json, gitignored, so regenerating needs a local copy).

The build writes nothing unless every check passes:
  * each paragraph §1–§2865 is found exactly once, on pages that never go backwards;
  * the words after each number match the paragraph's opening;
  * each heading in the flipbook's own contents (workspace.js) whose title matches one of
    ours (app/catechism_contents.json) sits on the page of its first paragraph or the one
    before (a heading can end a page whose next paragraph starts overleaf).
Failures name the pages to look at (pageNNNN_4.png in the cache). A paragraph whose
number is misread or misprinted is placed from its opening words alone, and printed.

Page numbers: the table stores the flipbook page index (1–924, the NNNN in asset names).
The viewer's URL numbers pages from the index minus `numerationOffset` (18), and the
number printed on the page differs again (index minus 20); neither is stored.

Needs Pillow and the `tesseract` binary (set TESSERACT to its path if it is not on PATH).
Run from services/api:
    python3 scripts/build_catechism_pages.py --cache ~/catechism-flipbook
"""
from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEXT_SOURCE = ROOT / "datapipeline" / "sources" / "catechism" / "us-edition" / "ccc-us.json"
CONTENTS = Path(__file__).resolve().parents[1] / "app" / "catechism_contents.json"
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "catechism_pages.json"

BASE = "https://www.usccb.org/sites/default/files/flipbooks/catechism"
LAST_PARAGRAPH = 2865
# The pages that hold numbered paragraphs: the Prologue (index 27) to the end of Part
# Four. The indexes and glossary from 709 on hold none.
FIRST_PAGE, LAST_PAGE = 27, 708
SIZE = 4  # the 1366 x 2050 text layer

# Geometry of the 1366-wide text layer. Paragraph numbers open lines at x 228-230 on
# every page; footnote numbers are indented to 267, margin references start near 150,
# and the running header (printed page number, part title) sits above y 190.
_NUMBER_LEFT = range(212, 250)
_BODY_TOP = 190
_SAME_LINE = 12  # px between word tops on one printed line (lines are 37 px apart)
_MATCH = 0.75  # difflib ratio between the OCR'd opening and ours
_OPENING = 40  # characters compared


def _fetch(url: str) -> bytes:
    # usccb.org's bot check answers 403 once a client has made many requests.
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 429, 503) or attempt == 3:
                raise
            time.sleep(10 * 2 ** attempt)
    raise AssertionError("unreachable")


def _cached(cache: Path, path: str) -> bytes:
    target = cache / Path(path).name
    if not target.exists():
        cache.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_fetch(f"{BASE}/{path}"))
    return target.read_bytes()


def publication(cache: Path) -> dict:
    """The flipbook's GUID, page-number offset and contents tree. Cached with the
    images, so delete the cache to build against a new publication."""
    index = _cached(cache, "index.html").decode()
    guid = re.search(r'GUID\s*=\s*"([0-9a-f]{32})"', index)
    if not guid:
        raise SystemExit("index.html carries no FBInit.GUID: the viewer changed, or "
                         "usccb.org answered with a bot check (delete it and retry later)")
    pager = json.loads(_cached(cache, "files/assets/common/pager.js"))
    workspace = json.loads(_cached(cache, "files/assets/html/workspace.js"))
    # Pages without a text layer (blanks) have no image to read.
    text_pages = [page for page in range(FIRST_PAGE, LAST_PAGE + 1)
                  if pager["pages"].get(str(page), {}).get("textLayer")]
    return {"guid": guid.group(1), "numeration_offset": pager["numerationOffset"],
            "text_pages": text_pages, "toc": workspace["toc"]}


def download(cache: Path, guid: str, pages: list[int]) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for page in pages:
        target = cache / f"page{page:04d}_{SIZE}.png"
        if target.exists() and target.stat().st_size:
            continue
        url = f"{BASE}/files/assets/common/page-textlayers/{target.name}?uni={guid}"
        target.write_bytes(_fetch(url))
        time.sleep(1)  # be gentle with usccb.org


def _words(cache: Path, page: int) -> list[dict]:
    """Tesseract's words on one page, cached beside the image as TSV."""
    tsv = cache / f"page{page:04d}_{SIZE}.tsv"
    if not tsv.exists():
        from PIL import Image

        layer = Image.open(cache / f"page{page:04d}_{SIZE}.png").convert("RGBA")
        # The layer is black text on transparency: flatten it onto white.
        flat = Image.new("RGBA", layer.size, (255, 255, 255, 255))
        flat.alpha_composite(layer)
        buffer = io.BytesIO()
        flat.convert("L").save(buffer, format="PNG")
        result = subprocess.run(
            [os.environ.get("TESSERACT", "tesseract"), "stdin", "stdout", "--psm", "3", "tsv"],
            input=buffer.getvalue(), capture_output=True, check=True,
        )
        tsv.write_bytes(result.stdout)
    rows = csv.DictReader(io.StringIO(tsv.read_text()), delimiter="\t", quoting=csv.QUOTE_NONE)
    return [
        {"left": int(r["left"]), "top": int(r["top"]), "text": r["text"].strip()}
        for r in rows if r["level"] == "5" and r["text"].strip()
    ]


def starts(words: list[dict]) -> list[tuple[int, str]]:
    """(number, the words after it) for each line that opens with a paragraph number."""
    found = []
    for number in words:
        digits = re.fullmatch(r"(\d{1,4})[^\w\s]{0,2}", number["text"])
        if not (digits and number["left"] in _NUMBER_LEFT and number["top"] >= _BODY_TOP):
            continue
        # The words level with the number, to its right. Tesseract's own line grouping
        # is not used: in an IN BRIEF block it reads the numbers as a separate column.
        rest = sorted((w for w in words if w["left"] > number["left"]
                       and abs(w["top"] - number["top"]) <= _SAME_LINE), key=lambda w: w["left"])
        found.append((int(digits.group(1)), " ".join(w["text"] for w in rest)))
    return found


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    return re.sub(r"[^a-z0-9]", "", text)


def matches(ocr: str, ours: str) -> bool:
    a, b = _normal(ocr)[:_OPENING], _normal(ours)[:_OPENING]
    if not a or not b:
        return False
    n = min(len(a), len(b))
    return difflib.SequenceMatcher(None, a[:n], b[:n]).ratio() >= _MATCH


def paragraph_texts() -> dict[int, str]:
    items = json.loads(TEXT_SOURCE.read_text())["items"]
    return {item["n"]: item["text"] for item in items if item["kind"] == "paragraph"}


def locate(cache: Path, texts: dict[int, str], text_pages: list[int],
           ) -> tuple[dict[int, int], list[str], list[str]]:
    """paragraph -> page, the repairs made (to print), and the problems (to fail on)."""
    pages: dict[int, list[int]] = {}
    misread: list[tuple[int, int, str]] = []  # (page, number as read, words after)
    for page in text_pages:
        for number, after in starts(_words(cache, page)):
            if number in texts and matches(after, texts[number]):
                pages.setdefault(number, []).append(page)
            elif len(_normal(after)) >= 10:
                misread.append((page, number, after))
    problems = [f"§{n} found on pages {p}" for n, p in sorted(pages.items()) if len(p) > 1]
    table = {n: p[0] for n, p in pages.items() if len(p) == 1}

    # A paragraph still missing may be one whose number is misread or misprinted (the
    # flipbook prints §1762 as "762", page 456). It is placed only from a line that opens
    # with a number, between
    # its neighbours' pages, whose words match its own opening, and only if exactly one
    # such line exists. Every repair is printed so a person can look at it.
    repairs = []
    for n in range(1, LAST_PARAGRAPH + 1):
        if n in table or n in pages:
            continue
        low = max((table[m] for m in table if m < n), default=FIRST_PAGE)
        high = min((table[m] for m in table if m > n), default=LAST_PAGE)
        found = [(page, read) for page, read, after in misread
                 if low <= page <= high and matches(after, texts[n])]
        if len(found) == 1:
            page, read = found[0]
            table[n] = page
            repairs.append(f"§{n} printed or read as {read!r} on page {page}; "
                           "placed by its opening words")
    return table, repairs, problems


def check_sequence(table: dict[int, int]) -> list[str]:
    errors = []
    missing = [n for n in range(1, LAST_PARAGRAPH + 1) if n not in table]
    for n in missing:
        around = [table[m] for m in (n - 1, n + 1) if m in table]
        errors.append(f"§{n} not found (look at pages {sorted(set(around)) or '?'})")
    previous = 0
    for n in range(1, LAST_PARAGRAPH + 1):
        if n in table:
            if table[n] < previous:
                errors.append(f"§{n} on page {table[n]} comes before §{n - 1}'s page {previous}")
            previous = table[n]
    return errors


def _flatten(nodes: list[dict]) -> list[dict]:
    out = []
    for node in nodes:
        out.append(node)
        out.extend(_flatten(node.get("children", [])))
    return out


def _title(text: str) -> str:
    text = re.sub(r"^(part|section|chapter|article|paragraph)\s+\w+[.:]?\s*", "", text, flags=re.I)
    return _normal(text)


# Flipbook headings known to sit further ahead of their first paragraph, at the page
# given. "The Ten Commandments" points at the Decalogue table (Exodus and Deuteronomy side
# by side) printed on the two pages before Section Two opens with §2052.
_CONTENTS_EXCEPTIONS = {("The Ten Commandments", 516)}


def check_contents(table: dict[int, int], toc: dict) -> tuple[list[str], int]:
    """Each flipbook heading that names one of our headings uniquely must sit on its
    first paragraph's page or the page before."""
    ours: dict[str, list[int]] = {}
    for node in _flatten(json.loads(CONTENTS.read_text())):
        ours.setdefault(_title(node["label"]), []).append(node["first"])
    errors, checked = [], 0
    for entry in _flatten(toc["children"]):
        firsts = ours.get(_title(entry["title"]))
        if (not firsts or len(firsts) != 1 or firsts[0] not in table
                or (entry["title"], entry["page"]) in _CONTENTS_EXCEPTIONS):
            continue  # unmatched, or a title used twice ("In Brief", "Introduction")
        checked += 1
        page = table[firsts[0]]
        if entry["page"] not in (page, page - 1):
            errors.append(f"heading {entry['title']!r} is on page {entry['page']}, "
                          f"its §{firsts[0]} on page {page}")
    return errors, checked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache", type=Path, required=True,
                        help="directory for the downloaded page images (outside the repo)")
    args = parser.parse_args()

    live = publication(args.cache)
    download(args.cache, live["guid"], live["text_pages"])
    table, repairs, problems = locate(args.cache, paragraph_texts(), live["text_pages"])
    if repairs:
        print("\n".join(repairs))
    errors = problems + check_sequence(table)
    contents_errors, checked = check_contents(table, live["toc"])
    errors += contents_errors
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(f"{len(errors)} problems; nothing written")
    if checked < 100:
        raise SystemExit(f"only {checked} headings matched the flipbook contents; nothing written")

    OUTPUT.write_text(json.dumps({
        "source": f"{BASE}/index.html",
        "guid": live["guid"],
        "numeration_offset": live["numeration_offset"],
        "flipbook_page": {str(n): table[n] for n in range(1, LAST_PARAGRAPH + 1)},
    }, indent=0) + "\n")
    print(f"wrote {len(table)} paragraphs to {OUTPUT.relative_to(ROOT)} "
          f"({checked} headings agree with the flipbook contents)")


if __name__ == "__main__":
    main()
