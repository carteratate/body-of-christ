"""Vendor the US edition of the Catechism of the Catholic Church (issue #279, B1).

TheoCorpus's `ccc.json` is vatican.va's English Catechism: the same translation as the
US edition but with UK spelling, dropped lines and the 1997 text of CCC 2267. The USCCB
allows only the edition approved for use in the United States. Catholic Cross Reference's
Catechism search (https://www.catholiccrossreference.online/catechism/) shows that text.

Two steps, so the site is asked for each page once:

    python3 scripts/fetch_us_catechism.py fetch   # ~116 POSTs, 30 s apart: about an hour
    python3 scripts/fetch_us_catechism.py build   # offline: cache -> sources/.../ccc-us.json

`fetch` keeps every response in a cache outside `sources/` (so the source lock never sees
it) and skips pages already cached, so an interrupted run resumes. It waits 30 seconds
between requests (the site's robots.txt asks for 10), sends a plain User-Agent, and stops
at the first non-200 response or error, with no retries. Run it once, by hand; it is not
part of the build.

`build` writes `sources/catechism/us-edition/ccc-us.json`:

    {"meta": {source, fetched_at, query, count},
     "items": [{"kind": "structure", "text", "first", "last", "footnotes": []},
               {"kind": "heading", "style", "text", "footnotes"},
               {"kind": "paragraph", "n", "text", "footnotes"}, ...]}

in reading order, where `text` is plain text with "\\n\\n" between inner paragraphs and each
footnote is `{n, text, at}`, `at` the character offset in `text` where marker `n` sits.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATAPIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATAPIPELINE))

URL = "https://www.catholiccrossreference.online/catechism/"
QUERY = "1-2865"
PER_PAGE = 25
LAST = 2865
DELAY_SECONDS = 30
USER_AGENT = "TheoCorpus/1.0 (+https://theo-corpus.com; one-time text check, 30 s delay)"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "theocorpus" / "ccr-catechism"
OUT = DATAPIPELINE / "sources" / "catechism" / "us-edition" / "ccc-us.json"


def _offsets() -> list[int]:
    return list(range(0, LAST, PER_PAGE))


def _cache_path(offset: int) -> Path:
    return CACHE / f"offset-{offset:04d}.json"


def _post(offset: int, token: int) -> dict:
    body = urllib.parse.urlencode(
        {"TOKEN": token, "lang": "en", "query": QUERY, "offset": offset}
    ).encode()
    request = urllib.request.Request(URL, data=body, headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"offset {offset}: HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or "html" not in payload:
        raise RuntimeError(f"offset {offset}: response has no html")
    if payload.get("per") not in (None, PER_PAGE, str(PER_PAGE)):
        raise RuntimeError(f"offset {offset}: page size {payload.get('per')!r}, expected {PER_PAGE}")
    return payload


def fetch(limit: int | None, offsets: list[int] | None = None) -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    todo = [o for o in (offsets or _offsets()) if not _cache_path(o).exists()]
    if limit is not None:
        todo = todo[:limit]
    print(f"{len(todo)} page(s) to fetch, {DELAY_SECONDS} s apart; cache {CACHE}")
    for i, offset in enumerate(todo):
        if i:
            time.sleep(DELAY_SECONDS)
        try:
            payload = _post(offset, token=i + 1)
        except Exception as exc:  # stop at the first problem; never retry
            print(f"stopped at offset {offset}: {exc}", file=sys.stderr)
            return 1
        payload["_fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _cache_path(offset).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"offset {offset}: ok ({len(payload['html'])} chars)", flush=True)
    return 0


def build() -> int:
    from ingest.ccc_us import drop_repeated_structure, parse_page, resolve

    missing = [o for o in _offsets() if not _cache_path(o).exists()]
    if missing:
        print(f"{len(missing)} page(s) not fetched yet, first offset {missing[0]}", file=sys.stderr)
        return 1
    items: list[dict] = []
    notes: dict[str, str] = {}
    fetched: list[str] = []
    for offset in _offsets():
        payload = json.loads(_cache_path(offset).read_text(encoding="utf-8"))
        fetched.append(payload["_fetched_at"])
        page_items, page_notes = parse_page(payload["html"])
        clash = set(page_notes) & set(notes)
        if clash:
            print(f"offset {offset}: notes printed on two pages: {sorted(clash)[:10]}", file=sys.stderr)
            return 1
        items.extend(page_items)
        notes.update(page_notes)
    items = resolve(drop_repeated_structure(items), notes)

    numbers = [item["n"] for item in items if item["kind"] == "paragraph"]
    expected = list(range(1, LAST + 1))
    if numbers != expected:
        seen = set(numbers)
        absent = [n for n in expected if n not in seen][:10]
        dupes = sorted({n for n in numbers if numbers.count(n) > 1})[:10]
        print(f"paragraph numbers wrong: absent {absent}, repeated {dupes}", file=sys.stderr)
        return 1
    empty = [item["n"] for item in items if item["kind"] == "paragraph" and not item["text"].strip()]
    if empty:
        print(f"empty paragraphs: {empty[:10]}", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "meta": {"source": URL, "fetched_at": max(fetched), "query": QUERY, "count": len(numbers)},
        "items": items,
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    headings = sum(item["kind"] in ("heading", "structure") for item in items)
    notes = sum(len(item["footnotes"]) for item in items)
    print(f"wrote {OUT}: {len(numbers)} paragraphs, {headings} headings, {notes} footnotes")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download pages not yet cached")
    f.add_argument("--limit", type=int, help="fetch at most this many pages")
    f.add_argument("--offset", type=int, action="append", dest="offsets",
                   help="fetch only this page offset (repeatable)")
    sub.add_parser("build", help="write ccc-us.json from the cache")
    args = parser.parse_args(argv)
    return fetch(args.limit, args.offsets) if args.command == "fetch" else build()


if __name__ == "__main__":
    sys.exit(main())
