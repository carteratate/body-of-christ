"""1.10a on the vendored sources: joined sentences spaced, trailing periods and ligatures
gone from labels, and every reviewed broken word found in its source and mended."""
import glob
import html
import json
import os
import re
from functools import lru_cache

import pytest

from checks.source_text import SOURCES
from normalize.text import BROKEN_WORDS_PATH
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

JOIN = re.compile(r"[a-z][.?!;:][”\"’)]?[A-Z][a-z]|[.;:]§")
ADDRESS = re.compile(r"://|www\.|@")
LIGATURE = re.compile("[æœÆŒ]")
with open(BROKEN_WORDS_PATH, encoding="utf-8") as f:
    BROKEN = json.load(f)


def _passages(built):
    for collection, documents in built.items():
        for d in documents:
            for p in d.passages:
                yield collection, d, p


def test_no_sentence_joins_outside_addresses(built):
    joins = [(c, p.anchor, tok) for c, _, p in _passages(built) for tok in p.content.split()
             if JOIN.search(tok) and not ADDRESS.search(tok)]
    assert joins == []


def test_no_trailing_periods_in_thml_authors_or_titles(built):
    labels = [(c, d.author, d.title) for c in ("church-fathers", "medieval")
              for d in built[c] if (d.author or "").endswith(".") or d.title.endswith(".")]
    assert labels == []


def test_no_ligatures_in_labels(built):
    hits = [(c, p.anchor) for c, d, p in _passages(built)
            if LIGATURE.search(" ".join((d.author or "", d.title, p.chapter_label,
                                         p.reference)))]
    assert hits == []


@lru_cache(maxsize=None)
def _source_text(collection: str) -> str:
    from ingest.theologians import COLLECTION, SOURCE_DIR

    # 5.6b's works build under the medieval key from their own folder.
    folders = [collection] + ([SOURCE_DIR] if collection == COLLECTION else [])
    parts = []
    paths = [p for folder in folders
             for p in glob.glob(os.path.join(SOURCES, folder, "**", "*"), recursive=True)]
    for path in sorted(paths):
        if os.path.isfile(path) and not path.endswith("Identifier"):
            with open(path, encoding="utf-8", errors="replace") as f:
                parts.append(html.unescape(f.read()))
    return "\n".join(parts)


@pytest.mark.parametrize("entry", BROKEN, ids=[e["broken"] for e in BROKEN])
def test_broken_word_is_in_its_sources_and_mended(built, entry):
    head, tail = entry["broken"].split("- ")
    # The source breaks the word at a line end, sometimes across markup or a page marker.
    in_source = re.compile(rf"(?<![A-Za-z]){re.escape(head)}-(?:\s|<[^>]+>|\[Page \d+\])+"
                           rf"{re.escape(tail)}(?![A-Za-z])")
    for collection in entry["collections"]:
        assert in_source.search(_source_text(collection)), collection
    in_build = re.compile(rf"(?<![A-Za-z]){re.escape(entry['broken'])}(?![A-Za-z])")
    assert [(c, p.anchor) for c, _, p in _passages(built) if in_build.search(p.content)] == []
