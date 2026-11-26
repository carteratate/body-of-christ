"""1.3d: older papal documents built from public-domain printings (ADR 0001).

Synthetic tests of the printing builder first; the vendored checks at the end need the
sources.
"""
import dataclasses
import json
import os
import re

import pytest

from ingest import papal_common, papal_printings
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


def test_a_printings_brackets_are_text_not_note_callers():
    """The site's page marks its notes "[39]"; a printing's notes are kept out by the
    builder, so its brackets stay (The Catholic Mind's "AAS [39] 1947")."""
    text = "with Christ (AAS [39] 1947, 552)."
    assert papal_common._clean(text, "test", callers=False) == text
    assert "[39]" not in papal_common._clean(text, "test")


def test_citations_become_source_lines_and_ibid_names_its_source():
    from ingest.papal_printings import mark_sources

    texts = ["Error one.\n\nAllocution Maxima quidem, June 9th, 1862.",
             "Error two. Ibid.",
             "Error three.\n\nIbid., and Encyclical Qui pluribus, Nov. 9th, 1846, etc.",
             "Error three b.\n\nIbid.",
             "Error four.\n\nLetters to the Archbishop of Munich, Dec. 11th, 1862, and Dec. 21st, 1863.",
             "Error five.\n\nIbid, Dec. 21st, 1863.", "Error six.\n\nIbid.",
             "A note naming the Encyclical Noscitis, Dec. 8th, 1849; Allocution Novos, Sept. 28th, 1860."]
    assert [t.split("\n\n")[-1] for t in mark_sources(texts)] == [
        "[Source: Allocution Maxima quidem, June 9th, 1862]",
        "[Source: Ibid., Allocution Maxima quidem, June 9th, 1862]",
        "[Source: Ibid., Allocution Maxima quidem, June 9th, 1862, and Encyclical Qui pluribus, "
        "Nov. 9th, 1846, etc]",
        "[Source: Ibid., Allocution Maxima quidem, June 9th, 1862, and Encyclical Qui pluribus, "
        "Nov. 9th, 1846, etc]",
        "[Source: Letters to the Archbishop of Munich, Dec. 11th, 1862, and Dec. 21st, 1863]",
        "[Source: Ibid., Letters to the Archbishop of Munich, Dec. 21st, 1863]",
        "[Source: Ibid., Letters to the Archbishop of Munich, Dec. 21st, 1863]",
        texts[-1]]
    with pytest.raises(ValueError, match="no source before"):
        mark_sources(["Error two. Ibid."])


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
        if p.marks_sources:
            # The source lines are the printed citations with their "Ibid." named.
            unmarked = papal_printings.build_printed(
                dataclasses.replace(p, marks_sources=False), _manifest(doc.collection)[
                    p.key.split("/", 1)[1]], doc.collection, src)
            assert [x.content for x in doc.passages] == papal_printings.mark_sources(
                [x.content for x in unmarked.passages]), p.key
            doc = unmarked
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


@vendored
def test_an_extract_holds_what_its_printing_lacks():
    """An extract's missing paragraphs are each held for permission, the site's page stays
    its held text, and its notes name them (1.3d step 6)."""
    import registry

    removals = registry.load_registry().removals
    extracts = 0
    for p, doc in _built():
        held = {r["anchor"] for r in removals if r["document_id"] == doc.id
                and r["scope"] == "passage" and r["reason"] == "awaiting-permission"}
        if not p.omits:
            assert not held and "held_text_url" not in doc.metadata and not doc.notes, p.key
            continue
        extracts += 1
        slug = p.key.split("/", 1)[1]
        assert held == {papal_common._anchor(slug, str(n)) for n in p.omits}, p.key
        assert not held & {x.anchor for x in doc.passages}, p.key
        assert doc.metadata["held_text_url"] == _manifest(doc.collection)[slug]["url"], p.key
        assert doc.notes and "not available on TheoCorpus" in doc.notes, p.key
    assert extracts


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


def test_a_signature_in_capitals_after_the_dating_line_joins_the_last_unit():
    p = _printing([("Join your prayers", 8)])
    toks = printed_tokens(p, [("p0", "Join your prayers to ours."),
                              ("p1", "Given at Rome, the 5th February of the year 1875."),
                              ("p2", "PIUS, P.P. IX.")])
    assert [t.number for t in toks] == [8] and toks[0].text.endswith("1875.\n\nPIUS, P.P. IX.")
    with pytest.raises(ValueError, match="in no unit"):
        printed_tokens(p, [("p0", "Join your prayers to ours."), ("p1", "PIUS, P.P. IX.")])


# ---------------------------------------------------------------- additions (5.9)

def test_an_addition_follows_its_paragraph_in_its_own_chapter(monkeypatch):
    from model import Document, Passage

    def para(n, k, chapter="test/bucket-0"):
        return Passage(content=f"Proposition {n}.", reference=f"Test, §{n}",
                       anchor=f"test/{n}", chapter_key=chapter,
                       chapter_label="Paragraphs", position=k, unit_label=f"§{n}")

    doc = Document(id="d", collection="papal-documents", title="Test", author="Pope Leo X",
                   year=1520, passages=[para(1, 0), para(2, 1, "test/bucket-1")])
    add = papal_printings.Addition(key="papal-documents/test", work="w",
                                   url="https://example.org/book", part="censure",
                                   label="Censure", after=1, why="a test")
    monkeypatch.setattr(papal_printings, "additions", lambda: {add.key: (add,)})
    monkeypatch.setattr(papal_printings, "read_text", lambda work: {
        "metadata": {"text_source": "ocr", "scan_id": "scan"},
        "passages": [{"id": "x", "text": "All and each we condemn."}]})
    out = papal_printings.with_additions(doc, "papal-documents", "test")
    assert [(p.anchor, p.position) for p in out.passages] == [
        ("test/1", 0), ("test/censure", 1), ("test/2", 2)]
    censure = out.passages[1]
    assert (censure.content, censure.chapter_key, censure.chapter_label, censure.unit_label,
            censure.reference) == ("All and each we condemn.", "test/censure", "Censure",
                                   "Censure", "Test, Censure")
    assert censure.metadata == {"pope": "Pope Leo X", "url": "https://example.org/book",
                                "source_url": "https://example.org/book",
                                "text_source": "ocr", "scan_id": "scan"}
    assert papal_printings.with_additions(doc, "papal-documents", "other") is doc
    monkeypatch.setattr(papal_printings, "additions", lambda: {add.key: (
        dataclasses.replace(add, after=9),)})
    with pytest.raises(ValueError, match="no paragraph 9"):
        papal_printings.with_additions(doc, "papal-documents", "test")
    # Inside a chapter it would split it in the reader.
    monkeypatch.setattr(papal_printings, "additions", lambda: {add.key: (add,)})
    one_chapter = dataclasses.replace(doc, passages=[para(1, 0), para(2, 1)])
    with pytest.raises(ValueError, match="does not end its chapter"):
        papal_printings.with_additions(one_chapter, "papal-documents", "test")


def test_every_addition_says_why_and_passed_its_gate():
    from ocr.fixes import read_text

    adds = [a for items in papal_printings.additions().values() for a in items]
    assert adds
    for a in adds:
        assert a.why and a.label and a.part and not a.part.isdigit(), a.key
        assert papal_printings.printing(*a.key.split("/", 1)) is None, a.key
        assert read_text(a.work)["gate"] == "pass", a.work


@vendored
def test_addition_coverage():
    """Every word of an addition's frozen text reaches its passages, and nothing else
    (0.1a's coverage, against the printing's pages)."""
    from ocr.fixes import read_text

    docs = {}
    for key, items in papal_printings.additions().items():
        collection, slug = key.split("/", 1)
        if collection not in docs:
            docs[collection] = {d.metadata["source_key"]: d for d in papal_common.build_documents(
                collection, os.path.join(_SOURCES, collection))}
        doc = docs[collection][key]
        for a in items:
            anchor = papal_common._anchor(slug, a.part)
            built = [p for p in doc.passages if p.anchor.split("/")[:2] == anchor.split("/")]
            assert built and all(p.voice is None for p in built), a.key
            assert _words(" ".join(p.content for p in built)) == _words(
                " ".join(p["text"] for p in read_text(a.work)["passages"])), a.key
