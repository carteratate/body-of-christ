"""1.3d: older papal documents built from public-domain printings (ADR 0001).

Synthetic tests of the printing builder first; the vendored checks at the end need the
sources.
"""
import json
import os
import re

import pytest

from ingest import papal_printings
from ingest.papal_printings import Printing, Unit, apply_fixes, printed_tokens

_DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SOURCES = os.path.join(_DATAPIPELINE, "sources")
_vendored = os.path.exists(os.path.join(_SOURCES, "encyclicals", "manifest.json"))
vendored = pytest.mark.skipif(not _vendored, reason="papal sources not vendored")
_WORD = re.compile(r"[A-Za-z0-9]+")


def _printing(units, editorial=()):
    return Printing(key="encyclicals/test", source="wikisource", file="x.html",
                    url="https://example.org/x", translation="A Magazine (1850)",
                    units=tuple(Unit(o, u) for o, u in units), editorial=tuple(editorial))


def test_blocks_take_the_units_the_alignment_names():
    p = _printing([("To all", "preamble"), ("First", 1), ("Still", "+"), ("Third", 3)],
                  editorial=[{"opens": "We print", "why": "the magazine's note"}])
    toks = printed_tokens(p, [("w0", "We print the letter below."), ("w1", "To all bishops."),
                              ("w2", "First paragraph."), ("w3", "Still the first."),
                              ("w4", "Third, which holds the site's 2 and 3."),
                              ("w5", "Given at Rome, 1 May 1850.")])
    assert [(t.kind, t.number) for t in toks] == [("preamble", None), ("para", 1), ("para", 3)]
    assert toks[1].text == "First paragraph.\n\nStill the first."
    assert [s.locator for s in toks[1].segments] == ["w2", "w3"]
    assert toks[2].text.endswith("Given at Rome, 1 May 1850.")


def test_a_block_no_unit_names_is_an_error():
    p = _printing([("First", 1)])
    with pytest.raises(ValueError, match="in no unit"):
        printed_tokens(p, [("w0", "First."), ("w1", "Something the alignment missed.")])
    with pytest.raises(ValueError, match="no block opens"):
        printed_tokens(_printing([("First", 1), ("Second", 2)]), [("w0", "First.")])


def test_a_fix_must_match_exactly_once():
    blocks = [("w0", "who commands die winds"), ("w1", "die die")]
    assert apply_fixes(blocks, [{"find": "commands die", "replace": "commands the"}])[0] == \
        ("w0", "who commands the winds")
    with pytest.raises(ValueError):
        apply_fixes(blocks, [{"find": "die", "replace": "the"}])
    with pytest.raises(ValueError):
        apply_fixes(blocks, [{"find": "absent", "replace": "x"}])


def test_every_printing_names_its_units_in_order():
    for p in papal_printings.printings().values():
        numbers = [u.unit for u in p.units if isinstance(u.unit, int)]
        assert numbers == sorted(numbers) and len(numbers) == len(set(numbers)), p.key
        assert all(u.unit in ("preamble", "+") or isinstance(u.unit, int) for u in p.units)
        assert all(f.get("why") for f in p.fixes), p.key
        assert all(e.get("why") for e in p.editorial), p.key


# ---------------------------------------------------------------- vendored checks

def _manifest(collection):
    with open(os.path.join(_SOURCES, collection, "manifest.json"), encoding="utf-8") as f:
        return {e["slug"]: e for e in json.load(f)}


def _built():
    for key, p in papal_printings.printings().items():
        collection, slug = key.split("/", 1)
        src = os.path.join(_SOURCES, collection)
        yield p, papal_printings.build_document(_manifest(collection)[slug], collection, src)


@vendored
def test_printing_coverage():
    """Every word the printing gives the text reaches the passages, in order (0.1a's
    coverage, measured against the printing rather than the site's page)."""
    for p, doc in _built():
        src = os.path.join(_SOURCES, p.key.split("/", 1)[0])
        kept = [t for _, t in papal_printings.blocks_of(p, src)
                if not any(t.startswith(e["opens"]) for e in p.editorial)]
        printed = _WORD.findall(" ".join(kept))
        built = _WORD.findall(" ".join(x.content for x in doc.passages))
        assert built == printed, p.key


@vendored
def test_printed_documents_point_at_their_printing():
    for p, doc in _built():
        assert doc.metadata["url"] == p.url and doc.translation == p.translation, p.key
        assert "papalencyclicals" not in doc.metadata["url"]
        for x in doc.passages:
            assert x.metadata["text_replaced"] == p.text_replaced, x.anchor
            assert x.metadata["url"] == p.url, x.anchor
            assert "papalencyclicals" not in x.content.lower(), x.anchor


def test_printed_documents_have_their_rights_row():
    """The printing's row carries the document; the site's `unknown` row is gone."""
    import registry

    with open(os.path.join(_DATAPIPELINE, "rights_inventory.json"), encoding="utf-8") as f:
        rows = json.load(f)
    for key in papal_printings.printings():
        collection, slug = key.split("/", 1)
        did = registry.resolve_document_id(collection, key, (collection, slug))
        mine = [r for r in rows if r.get("document_id") == did]
        assert len(mine) == 1, key
        assert mine[0]["status"].startswith("pd-us-") and mine[0]["planned_for"] is None, key
        assert "papalencyclicals" not in mine[0]["source_url"], key


def test_source_lock_reads_transcriptions_as_adapter_input():
    with open(os.path.join(_DATAPIPELINE, "source_lock.json"), encoding="utf-8") as f:
        lock = {e["path"]: e for e in json.load(f)}
    for key, p in papal_printings.printings().items():
        if p.source == "wikisource":
            entry = lock[f"{key.split('/', 1)[0]}/{p.file}"]
            assert entry["role"] == "adapter-input" and entry["url"] == p.url, key
