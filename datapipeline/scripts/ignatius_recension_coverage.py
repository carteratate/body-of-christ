"""Coverage check for the Ignatian recension split (corpus-cleanup 1.8c), run locally.

    cd datapipeline
    python3 scripts/ignatius_recension_coverage.py --cache <dir> [--out <file.md>]

The adapter keeps the first paragraph of each unit of the seven genuine letters as the
shorter recension (the Decision log's "Genuine Ignatius letters"), which this check must
prove chapter by chapter. The independent copy is Wikisource's proofread transcription
of the ANF volume 1 scan (`Page:Ante-Nicene Fathers volume 1.djvu/<n>`), which sets the
two columns apart under their printed heads, "Shorter." and "Longer.", in sections named
`Short<n>` and `Long<n>`. The pages are downloaded once into `--cache`.

For each unit (the greeting and each chapter) it compares paragraph 1 and paragraph 2 of
the vendored source with the scan's shorter column for that chapter, and passes when
paragraph 1 scores at least 0.9 and paragraph 2 lower. The table holds similarities only,
no text. Exits 1 when a unit fails.
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

from ingest import church_fathers as cf  # noqa: E402
from ingest.common import _block_text, direct_blocks, iter_chapters  # noqa: E402

API = "https://en.wikisource.org/w/api.php"
PAGE = "Page:Ante-Nicene Fathers volume 1.djvu/{}"
FIRST_PAGE, LAST_PAGE = 159, 290       # Ephesians opens on 159; Polycarp ends before 290
PASS = 0.9
# The scan's heading code for each letter, by its work div.
# Smyrnaeans' last chapter (XIII) is named "C" in the transcription.
SCAN_NAMES = {("Smy", "13"): "C"}
LETTERS = {"v.ii": "Eph", "v.iii": "Mag", "v.iv": "Tra", "v.v": "Rom", "v.vi": "Phi",
           "v.vii": "Smy", "v.viii": "Pol"}
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


def roman(numeral: str) -> int:
    total, prev = 0, 0
    for ch in reversed(numeral.lower()):
        value = _ROMAN[ch]
        total += -value if value < prev else value
        prev = max(prev, value)
    return total


def fetch(cache: str, n: int) -> str:
    path = os.path.join(cache, f"{n}.json")
    if not os.path.exists(path):
        query = urllib.parse.urlencode({"action": "parse", "page": PAGE.format(n),
                                        "prop": "wikitext", "format": "json"})
        request = urllib.request.Request(f"{API}?{query}",
                                         headers={"User-Agent": "TheoCorpus-coverage/1.0"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8")
                json.loads(body)
                break
            except (OSError, ValueError):
                time.sleep(2 ** attempt)
        else:
            raise SystemExit(f"could not fetch page {n}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        time.sleep(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("parse", {}).get("wikitext", {}).get("*", "")


def plain(wikitext: str) -> str:
    """The words of a stretch of wikitext: no notes, templates or markup."""
    text = re.sub(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", " ", wikitext, flags=re.DOTALL)
    text = re.sub(r"<noinclude>.*?</noinclude>", " ", text, flags=re.DOTALL)
    # A word hyphenated across pages is given whole where it starts.
    text = re.sub(r"\{\{hws\|[^|{}]*\|([^|{}]*)\}\}", r"\1", text)
    text = re.sub(r"\{\{hwe\|[^{}]*\}\}", "", text)
    for _ in range(3):
        text = re.sub(r"\{\{(?:sc|small-caps|smaller|larger|x-larger|c|uc)\|([^{}]*)\}\}",
                      r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"^\s*(Shorter|Longer)\.\s*", "", html.unescape(text))
    return " ".join(text.split())


def scan_columns(cache: str) -> dict[str, dict[str, str]]:
    """{letter code: {"ShortPre" / "Short<n>" / "Long<n>": text}} from the scan's pages."""
    out: dict[str, dict[str, str]] = defaultdict(lambda: defaultdict(str))
    letter = None
    for n in range(FIRST_PAGE, LAST_PAGE + 1):
        text = fetch(cache, n)
        # A section runs from one tag naming it to the next; a page may open one with an
        # end tag by mistake (page 236 does).
        tags = list(re.finditer(r'<section (?:begin|end)="([^"]+)"\s*/>', text))
        opened = None
        for tag in tags:
            if opened is None or opened.group(1) != tag.group(1):
                opened = tag
                continue
            name, body = tag.group(1), text[opened.end():tag.start()]
            opened = None
            if name.startswith("Head"):
                letter = name[4:]
            elif letter and re.match(r"^(Short|Long)(Pre|\d+|C)$", name):
                out[letter][name] += " " + plain(body)
    return out


def similarity(a: str, b: str) -> float:
    words = lambda s: re.findall(r"[a-z]+", s.lower().replace("æ", "ae"))  # noqa: E731
    return difflib.SequenceMatcher(None, words(a), words(b), autojunk=False).ratio()


def units(filename: str, work_id: str):
    """(label, chapter number or "Pre", paragraphs) of each unit of a letter."""
    root = cf._read_root(os.path.join(cf._SRC_DIR, filename))
    parent_map = cf._build_parent_map(root)
    work = next(e for e in root.iter() if e.get("id") == work_id)
    yield work_id, "Pre", [_block_text(b) for b in direct_blocks(work) if _block_text(b)]
    for _, elem in iter_chapters(work, parent_map):
        m = re.match(r"^Chapter ([IVXLC]+)\b", elem.get("title") or elem.get("shorttitle")
                     or "")
        number = str(roman(m.group(1))) if m else "?"
        yield elem.get("id"), number, [_block_text(b) for b in direct_blocks(elem)
                                       if _block_text(b)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cache", required=True, help="folder for the downloaded pages")
    parser.add_argument("--out", help="write the table here as Markdown")
    args = parser.parse_args(argv)
    os.makedirs(args.cache, exist_ok=True)
    scan = scan_columns(args.cache)
    lines = ["| Letter | Unit | Chapter | Paragraphs | P1 vs shorter | P2 vs shorter | "
             "Result |", "|---|---|---|---|---|---|---|"]
    failing = 0
    for filename, work_id in sorted(cf._RECENSIONS):
        code = LETTERS[work_id]
        for uid, number, paragraphs in units(filename, work_id):
            shorter = scan[code].get(f"Short{SCAN_NAMES.get((code, number), number)}", "")
            which = cf._RECENSION_OVERRIDE.get(uid)
            s1 = similarity(paragraphs[0], shorter) if paragraphs and shorter else 0.0
            s2 = similarity(paragraphs[1], shorter) if len(paragraphs) > 1 and shorter \
                else None
            if which == "long":
                # The unit prints the longer column alone: it must not be the shorter.
                ok = s1 < PASS
            elif which == "short":
                ok = s1 >= PASS
            else:
                ok = s1 >= PASS and s2 is not None and s2 < s1
            failing += not ok
            lines.append(f"| {code} | {uid} | {number} | {len(paragraphs)}"
                         f"{' (' + which + ')' if which else ''} | {s1:.3f} | "
                         f"{'' if s2 is None else f'{s2:.3f}'} | {'pass' if ok else 'FAIL'} |")
    table = "\n".join(lines)
    print(table)
    print(f"{failing} failing of {len(lines) - 2} units")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(table + "\n")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
