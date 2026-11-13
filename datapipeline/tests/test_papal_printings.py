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
_LIGATURES = str.maketrans({"æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe"})


def _words(text: str) -> list[str]:
    """Words as the passages hold them: the cleaner writes ligatures out."""
    return _WORD.findall(text.translate(_LIGATURES))


def _printing(units, editorial=()):
    return Printing(key="encyclicals/test", source="wikisource", file="x.html", work=None,
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
        assert all(u.unit in ("preamble", "preface", "section", "epigraph", "+", "omit")
                   or isinstance(u.unit, int)
                   for u in p.units)
        assert all(u.until and u.why for u in p.units if u.unit == "omit"), p.key
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
    coverage, measured against the printing rather than the site's page). The only words
    left out are an editor's (`editorial` blocks, `omit` headings) and the numbers a
    printing sets before its paragraphs."""
    import difflib

    for p, doc in _built():
        src = os.path.join(_SOURCES, p.key.split("/", 1)[0])
        blocks = papal_printings.blocks_of(p, src)
        toks = printed_tokens(p, blocks)
        built = _words(" ".join(x.content for x in doc.passages))
        assert built == _words(" ".join(t.text for t in toks)), p.key
        kept = [t for _, t in blocks if not any(t.startswith(e["opens"]) for e in p.editorial)]
        printed = _words(" ".join(kept))
        tokened = _words(" ".join(t.text for t in toks))
        omitted = {w for u in p.units if u.unit == "omit"
                   for t in kept if t.startswith(u.opens) for w in _words(t[:t.find(u.until)])}
        numbers = {str(u.unit) for u in p.units if isinstance(u.unit, int)}
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, printed, tokened,
                                                          autojunk=False).get_opcodes():
            assert op in ("equal", "delete"), (p.key, printed[i1:i2], tokened[j1:j2])
            if op == "delete":
                assert set(printed[i1:i2]) <= omitted | numbers, (p.key, printed[i1:i2])


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


def test_scanned_printings_passed_their_gate():
    """A scanned printing's text is published only once 1.2f's gate passed: the
    unrecognized-word rate and the person's sampled check against the page images."""
    from ocr.fixes import read_text

    for p in papal_printings.printings().values():
        if p.source == "ocr":
            assert read_text(p.work)["gate"] == "pass", p.work


def test_a_heading_run_into_the_text_is_cut_off_and_numbers_are_not_text():
    p = _printing([])
    p = Printing(**{**p.__dict__, "units": (
        Unit("THE LETTER", "omit", "To our Brethren", "the magazine's title"),
        Unit("To our Brethren", "preamble"),
        Unit("Health", "preamble", "With how great care"),
        Unit("With how great care", 1), Unit("§ I. Errors", "section"), Unit("2. There", 2),
        Unit("N.B. To the", "epigraph"))})
    toks = printed_tokens(p, [("p0", "THE LETTER of Pius IX. To our Brethren, all bishops."),
                              ("p1", "Health and Benediction. With how great care we write."),
                              ("p2", "§ I. Errors of our time."), ("p3", "2. There exists no God."),
                              ("p4", "N.B. To the errors above belong others.")])
    assert [(t.kind, t.number, t.text) for t in toks] == [
        ("preamble", None, "To our Brethren, all bishops."),
        ("preamble", None, "Health and Benediction."),
        ("para", 1, "With how great care we write."),
        ("section", None, "§ I. Errors of our time."),
        ("para", 2, "There exists no God."),
        ("epigraph", None, "N.B. To the errors above belong others.")]


def test_scanned_blocks_rejoin_a_paragraph_and_a_word_broken_between_passages():
    text = {"passages": [{"id": "a", "text": "One.\n\nTwo runs on and philoso-"},
                         {"id": "b", "text": "phy; three.\n\nFour.", "continues": True},
                         {"id": "c", "text": "and five.", "continues": True}]}
    assert papal_printings.ocr_blocks(text) == [
        ("p0", "One."), ("p1", "Two runs on and philosophy; three."), ("p2", "Four. and five.")]
