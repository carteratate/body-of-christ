"""Check the text fragments of passage links into vatican.va (corpus-cleanup 2.4e, #292).

    cd datapipeline
    python3 -m checks.source_links           # report only
    python3 -m checks.source_links --write   # also rewrite the API's list of misses

An excerpt-only passage from vatican.va links to its document's page with a text
fragment of its opening words (`services/api/app/source_links.py`, loaded here by path so
both use one rule). A browser scrolls to the first place on the page where those words
stand within one block of text, matching case-insensitively and on whole words. This check
does the same against the vendored copy of each page (found in `source_lock.json` by the
document's `metadata.url`):

- found: the words stand on the page once, or more than once with the passage's own
  place the first, judged by which match the text after it resembles most;
- repeated: they stand on the page more than once and an earlier place resembles the
  passage less, so the browser would stop short of it;
- missing: they do not stand on the page;
- no fragment: the passage's opening gives too few reliable words, so it has none.

Missing and repeated passages keep the plain URL: `--write` lists them in
`services/api/app/source_link_misses.json`, which the API reads. The passages are read
from the live database, read-only, for every live document whose `metadata.url` is on
vatican.va, whatever its reader access, so a document made excerpt-only later is covered.
Rerun the check, with `--write`, after a publish that changes those passages.

`--build <collection> --source-key <key> ...` reads the named documents' passages from
the build instead, under the IDs they will carry live, for documents a later publish moves
onto vatican.va (1.3c's 23 papal documents, whose live text is still papalencyclicals.net's).
With `--write` it replaces only those passages' entries, under `from_build`; a later run on
the live database keeps the `from_build` entries it did not read, so a rerun before that
publish cannot drop them, and drops them once the documents are live on vatican.va.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from difflib import SequenceMatcher

from bs4 import BeautifulSoup

from checks.source_text import SOURCES, _html_blocks

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_APP = os.path.join(os.path.dirname(HERE), "services", "api", "app")
MISSES = os.path.join(API_APP, "source_link_misses.json")

_spec = importlib.util.spec_from_file_location(
    "api_source_links", os.path.join(API_APP, "source_links.py"))
source_links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(source_links)

# How much text after a match is compared with the passage.
_COMPARE_CHARS = 300

_PASSAGES_SQL = r"""
    SELECT c.id::text AS id, d.id::text AS document_id, d.title, d.reader_access,
           d.metadata->>'url' AS url, c.content
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.metadata->>'url' ~ '^https?://([a-z0-9-]+\.)*vatican\.va(/|$)'
      {visible}
    ORDER BY d.title, c.position
"""


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def page_blocks(path: str) -> list[str]:
    """The page's text as a browser searches it: one string per block, scripts, styles
    and the head left out."""
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    for el in soup(["script", "style", "noscript", "head", "template"]):
        el.decompose()
    return [_normalize(b.text) for b in _html_blocks(soup.body or soup) if b.text.strip()]


def matches(blocks: list[str], fragment: str) -> list[str]:
    """The page text from each place the fragment stands as whole words within one
    block, in page order, to the end of that block."""
    words = _normalize(fragment)
    pattern = re.compile(
        (r"(?<!\w)" if words[0].isalnum() else "") + re.escape(words)
        + (r"(?!\w)" if words[-1].isalnum() else ""))
    return [b[m.start():] for b in blocks for m in pattern.finditer(b)]


def first_is_passage(found: list[str], fragment: str, content: str) -> bool:
    """Whether the first match is where the passage stands: the text after it resembles
    the passage's text after its fragment more than at any later match. A tie cannot tell
    the places apart (two questions printed alike in the Compendium, 5.5), so it is not."""
    text = _normalize(content)
    start = text.find(_normalize(fragment))
    expected = text[start if start >= 0 else 0:][:_COMPARE_CHARS]
    scores = [SequenceMatcher(None, expected, f[:_COMPARE_CHARS], autojunk=False).ratio()
              for f in found]
    return len(scores) == 1 or scores[0] > max(scores[1:])


def vendored_pages() -> dict[str, str]:
    """Each source URL's vendored file. A file still in `_incoming/` is used only when the
    URL has no other."""
    with open(os.path.join(HERE, "source_lock.json")) as f:
        lock = json.load(f)
    pages: dict[str, str] = {}
    for entry in sorted(lock, key=lambda e: e["path"].startswith("_incoming/")):
        if entry.get("url"):
            pages.setdefault(entry["url"], os.path.join(SOURCES, entry["path"]))
    return pages


def classify(passages, pages: dict[str, str]):
    """(outcome per passage id, rows of the report). Outcomes: found, repeated, missing,
    no-fragment, no-page."""
    outcomes: dict[str, str] = {}
    by_document: dict[str, Counter] = {}
    cache: dict[str, list[str]] = {}
    for p in passages:
        path = pages.get(p["url"])
        fragment = source_links.fragment_text(p["content"])
        if path is None or not os.path.exists(path):
            outcome = "no-page"
        elif fragment is None:
            outcome = "no-fragment"
        else:
            if path not in cache:
                cache[path] = page_blocks(path)
            found = matches(cache[path], fragment)
            if not found:
                outcome = "missing"
            elif len(found) == 1 or first_is_passage(found, fragment, p["content"]):
                outcome = "found"
            else:
                outcome = "repeated"
        outcomes[p["id"]] = outcome
        by_document.setdefault(p["title"], Counter())[outcome] += 1
    return outcomes, by_document


async def _read_passages(database_url: str) -> list[dict]:
    import asyncpg
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        has_retired = await conn.fetchval(
            "SELECT count(*) = 2 FROM information_schema.columns WHERE table_schema = "
            "'public' AND table_name IN ('chunks', 'documents') AND column_name = 'retired_at'")
        visible = ("AND c.retired_at IS NULL AND d.retired_at IS NULL"
                   if has_retired else "")
        return [dict(r) for r in await conn.fetch(_PASSAGES_SQL.format(visible=visible))]
    finally:
        await conn.close()


def write_misses(outcomes: dict[str, str], path: str = MISSES,
                 build_keys: list[str] | None = None) -> list[str]:
    """Replace the list. Refuses when a page was not found: the vendored sources are
    gitignored, and a list written without them would drop known misses.

    With `build_keys`, `outcomes` are those built documents' passages: only their entries
    change, kept under `from_build`. Without, the live run's list is written, and the
    `from_build` entries it did not read are kept."""
    if "no-page" in outcomes.values():
        raise SystemExit("some vendored pages are missing (see no-page above); "
                         "the list was not rewritten")
    found = {i for i, o in outcomes.items() if o in ("missing", "repeated")}
    previous = {}
    if os.path.exists(path):
        with open(path) as f:
            previous = json.load(f)
    built = previous.get("from_build") or {"source_keys": [], "chunk_ids": []}
    if build_keys is None:
        built["chunk_ids"] = sorted(set(built["chunk_ids"]) - set(outcomes))
        counts = dict(sorted(Counter(outcomes.values()).items()))
        live = found
    else:
        built = {"generated": date.today().isoformat(),
                 "source_keys": sorted(set(built["source_keys"]) | set(build_keys)),
                 "counts": dict(sorted(Counter(outcomes.values()).items())),
                 "chunk_ids": sorted(set(built["chunk_ids"]) - set(outcomes) | found)}
        counts = previous.get("counts", {})
        live = set(previous.get("chunk_ids", [])) - set(previous.get("from_build", {})
                                                         .get("chunk_ids", [])) - set(outcomes)
    misses = sorted(live | set(built["chunk_ids"]))
    data = {
        "_about": "Passages whose vatican.va link keeps the plain URL. Generated by "
                  "datapipeline/checks/source_links.py --write; do not edit by hand.",
        "generated": previous.get("generated") if build_keys is not None
        else date.today().isoformat(),
        "counts": counts,
        "chunk_ids": misses,
    }
    if built["chunk_ids"] or build_keys is not None:
        data["from_build"] = built
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    return misses


def built_passages(collection: str, source_keys: list[str]) -> list[dict]:
    """The named built documents' passages on vatican.va, under their registry IDs."""
    from checks.report import SOURCE_ADAPTERS, placeholder_credentials
    from release.remap import default_passage_id

    placeholder_credentials()
    documents = [d for d in SOURCE_ADAPTERS[collection]()
                 if d.metadata.get("source_key") in source_keys]
    missing = set(source_keys) - {d.metadata["source_key"] for d in documents}
    if missing:
        raise SystemExit(f"not built: {sorted(missing)}")
    out = []
    for d in documents:
        if not source_links.is_vatican(d.metadata.get("url")):
            raise SystemExit(f"{d.metadata['source_key']} is not taken from vatican.va")
        out += [{"id": default_passage_id(d, p), "document_id": d.id, "title": d.title,
                 "url": d.metadata["url"], "content": p.content} for p in d.passages]
    return out


def report(outcomes: dict[str, str], by_document: dict[str, Counter]) -> str:
    counts = Counter(outcomes.values())
    total = sum(counts.values())
    checked = counts["found"] + counts["repeated"] + counts["missing"]
    lines = [f"{total} passages in {len(by_document)} documents"]
    for key in ("found", "repeated", "missing", "no-fragment", "no-page"):
        lines.append(f"  {key:12} {counts[key]:6}  {counts[key] / total:.1%}" if total else "")
    if checked:
        lines.append(f"miss rate (missing or repeated, of passages with a fragment): "
                     f"{(counts['missing'] + counts['repeated']) / checked:.2%}")
    worst = sorted(by_document.items(),
                   key=lambda kv: -(kv[1]["missing"] + kv[1]["repeated"]))[:15]
    lines.append("documents with the most misses:")
    for title, c in worst:
        if c["missing"] + c["repeated"]:
            lines.append(f"  {c['missing']:4} missing {c['repeated']:4} repeated  "
                         f"of {sum(c.values()):4}  {title}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true",
                        help=f"rewrite {os.path.relpath(MISSES, HERE)}")
    parser.add_argument("--build", metavar="COLLECTION",
                        help="read these documents from the build, not the live database")
    parser.add_argument("--source-key", action="append", default=[],
                        help="with --build: a document's source key (repeatable)")
    args = parser.parse_args(argv)
    if args.build:
        if not args.source_key:
            parser.error("--build needs at least one --source-key")
        passages = built_passages(args.build, args.source_key)
    else:
        from config import settings
        passages = asyncio.run(_read_passages(settings.DATABASE_URL))
    outcomes, by_document = classify(passages, vendored_pages())
    print(report(outcomes, by_document))
    if args.write:
        misses = write_misses(outcomes, build_keys=args.source_key if args.build else None)
        print(f"wrote {len(misses)} misses to {os.path.relpath(MISSES, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
