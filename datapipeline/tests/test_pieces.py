"""Split pieces cite their own text (corpus-cleanup 1.10c): `pack_units`, `piece_reference`
and the adapters that use them."""
import os
import random
import re
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.common import DISPLAY_PASSAGE_MAX_OVERSHOOT, split_display_passage
from ingest.pieces import Segment, cut_at_units, pack_text, pack_units, piece_reference

CAP = 3500


def _sentences(rng: random.Random, chars: int) -> str:
    out, n = [], 0
    while n < chars:
        s = " ".join(rng.choice(["grace", "law", "the", "Church", "faith", "of", "and"])
                     for _ in range(rng.randint(4, 18))).capitalize() + "."
        out.append(s)
        n += len(s) + 1
    return " ".join(out)


def _units(seed: int) -> list[tuple[None, str]]:
    rng = random.Random(seed)
    sizes = [rng.choice([60, 400, 1200, 2500, 3400, 3600, 5200, 9000])
             for _ in range(rng.randint(1, 9))]
    return [(None, _sentences(rng, n)) for n in sizes]


def test_pack_units_never_splits_a_unit_under_cap():
    for seed in range(200):
        units = _units(seed)
        pieces = pack_units(units, CAP)
        for k, (_, text) in enumerate(units):
            body = text.strip()
            holders = [p for p in pieces if p.first <= k <= p.last]
            if len(body) <= CAP:
                assert len(holders) == 1, (seed, k)
                assert body in holders[0].text
        for p in pieces:
            # Over the cap only where a whole unit ends the piece (the splitter's allowance).
            assert len(p.text) <= CAP + DISPLAY_PASSAGE_MAX_OVERSHOOT


def test_pack_units_keeps_every_character():
    for seed in range(200):
        units = _units(seed)
        pieces = pack_units(units, CAP)
        joined = "".join(t for _, t in units)
        assert re.sub(r"\s", "", "".join(p.text for p in pieces)) == re.sub(r"\s", "", joined)


def test_pack_units_reports_first_unit_and_opening():
    head, long, tail = "A heading line.", _sentences(random.Random(1), 6000), "A tail."
    pieces = pack_units([(None, head), (None, long), (None, tail)], CAP)
    # The heading shares the long paragraph's first piece, as split_display_passage cut it.
    assert [(p.first, p.last, p.opens) for p in pieces][0] == (0, 1, True)
    assert all(p.first == 1 and not p.opens for p in pieces[1:])
    assert pieces[-1].text.endswith(tail)


def test_pack_units_keeps_split_display_passage_cuts_between_units():
    # Where every cut already falls between units, packing changes nothing (no churn).
    units = [(None, _sentences(random.Random(k), 1500)) for k in range(6)]
    text = "\n\n".join(t for _, t in units)
    assert [p.text for p in pack_units(units, CAP)] == split_display_passage(text, CAP)


def test_pack_units_with_slices_returns_slices():
    text = "First verse here. {{v:2}} Second verse. {{v:3}} Third."
    units = [("1:1", "First verse here. "), ("1:2", "{{v:2}} Second verse. "),
             ("1:3", "{{v:3}} Third.")]
    (piece,) = pack_units(units, CAP, sep="")
    assert piece.text == text and (piece.first, piece.last) == (0, 2)


def test_split_display_passage_never_cuts_a_kept_span():
    rng = random.Random(7)
    paras = [_sentences(rng, n) for n in (3000, 3000, 900)]
    text = "\n\n".join(paras)
    starts = [text.index(p) for p in paras]
    keep = [(s, s + len(p)) for s, p in zip(starts, paras)]
    for piece in split_display_passage(text, CAP, keep):
        assert piece in paras or all(p in piece or p not in text for p in paras)
        start = text.index(piece)
        for a, b in keep:
            assert not (a < start < b) and not (a < start + len(piece) < b)


def test_cut_at_units_keeps_an_opening_quote_with_its_paragraph():
    text = "One paragraph ends. “A quoted one” follows."
    segments = [Segment("e1", "One paragraph ends."), Segment("e2", "“A quoted one” follows.")]
    assert cut_at_units(text, segments) == [(0, "One paragraph ends. "),
                                            (1, "“A quoted one” follows.")]


def test_pack_text_cuts_only_between_elements():
    paras = [_sentences(random.Random(k), 2000) for k in range(3)]
    text = " ".join(paras)
    segments = [Segment(f"e{k}", p) for k, p in enumerate(paras)]
    assert pack_text(text, segments, CAP) == paras


def test_piece_reference_range_and_part_forms():
    assert piece_reference("Genesis", "1:14", "1:31", 2, 2) == "Genesis 1:14–31"
    assert piece_reference("Genesis", "1:31", "2:3", 1, 1) == "Genesis 1:31–2:3"
    assert piece_reference("Genesis", "1:5", "1:5", 1, 3) == "Genesis 1:5"
    assert piece_reference("Genesis", "10:1", "1:9", 1, 1) == "Genesis 10:1–1:9"
    assert piece_reference("Confessions, Book I", None, None, 2, 3) == \
        "Confessions, Book I (part 2 of 3)"
    assert piece_reference("Lumen Gentium, §8", None, None, 1, 1) == "Lumen Gentium, §8"


# --------------------------------------------------------------------------- adapters

def test_thml_pieces_cite_their_part_and_no_author():
    import defusedxml.ElementTree as ET
    from ingest.thml_doc import make_doc
    rng = random.Random(3)
    paras = "".join(f"<p id='ii.i-p{k}'>{_sentences(rng, 1600)}</p>" for k in range(1, 5))
    root = ET.fromstring(f"<div1 id='ii'><div2 id='ii.i' title='Chapter 1'>{paras}</div2>"
                         f"<div2 id='ii.ii' title='Chapter 2'><p>{'word ' * 40}</p></div2></div1>")
    doc = make_doc(collection="church-fathers", filename="f.xml", author="Methodius",
                   title="The Banquet", chapters=[(None, d) for d in root],
                   source_key="church-fathers/unregistered.xml#ii")
    refs = [p.reference for p in doc.passages]
    assert refs == ["The Banquet, Chapter 1 (part 1 of 2)", "The Banquet, Chapter 1 (part 2 of 2)",
                    "The Banquet, Chapter 2"]
    assert doc.passages[1].anchor == "ii.i/from-p3"
    assert all(p.content.count("\n\n") == 1 for p in doc.passages[:2])   # two whole <p>s each


def test_thml_pieces_count_their_own_notes():
    import defusedxml.ElementTree as ET
    from ingest.thml_doc import make_doc
    rng = random.Random(4)
    a, b = _sentences(rng, 3000), _sentences(rng, 3000)
    root = ET.fromstring(
        f"<div1 id='ii'><div2 id='ii.i' title='Chapter 1'>"
        f"<p id='ii.i-p1'>{a}<note n='1'>Matt. xxiv. 15.</note></p>"
        f"<p id='ii.i-p2'>{b}<note n='2'>Literally, to.</note><note n='3'>Rom. i. 1.</note></p>"
        f"</div2></div1>")
    doc = make_doc(collection="church-fathers", filename="f.xml", author="A", title="T",
                   chapters=[(None, d) for d in root], source_key="church-fathers/unregistered.xml#ii")
    first, second = doc.passages
    assert first.metadata["editor_note_count"] == 1
    assert [f["text"] for f in first.metadata["footnotes"]] == ["Matt. xxiv. 15."]
    assert first.metadata["footnotes"][0]["at"] == len(first.content)
    assert second.metadata["editor_note_count"] == 2
    assert [f["text"] for f in second.metadata["footnotes"]] == ["Rom. i. 1."]


def test_distinct_titles_keeps_piece_suffix():
    from model import Document, Passage
    from ingest.thml_doc import distinct_titles
    p = Passage(content="x", reference="Fragments, Chapter 1 (part 2 of 2)", anchor="a",
                chapter_key="a", chapter_label="Chapter 1", position=0)
    docs = [Document(id="1", collection="church-fathers", title="Fragments", author="Papias",
                     passages=[p]),
            Document(id="2", collection="church-fathers", title="Fragments", author="Methodius")]
    distinct_titles(docs)
    assert p.reference == "Fragments of Papias, Chapter 1 (part 2 of 2)"


def _verses(n: int, chars: int) -> list[tuple[int, int, str]]:
    rng = random.Random(n)
    return [(5, v, _sentences(rng, chars)) for v in range(1, n + 1)]


def test_bible_pieces_cite_their_own_verses():
    from ingest.bible import _join_with_verse_markers, _pieces
    from normalize.text import clean_text
    verses = _verses(30, 300)
    content = clean_text(_join_with_verse_markers(verses))
    pieces = _pieces("Tobit", 5, verses, content, "tobit/5/1")
    assert len(pieces) > 1
    last = 0
    for text, ref, label, anchor, *_ in pieces:
        first_v = int(label)
        markers = [int(m) for m in re.findall(r"\{\{v:(\d+)\}\}", text)]
        assert not text.startswith("{{v:")
        assert first_v == last + 1                     # no verse cut, none skipped
        last = markers[-1] if markers else first_v
        expected = f"Tobit 5:{first_v}" + (f"–{last}" if last != first_v else "")
        assert ref == expected
        assert anchor == ("tobit/5/1" if first_v == 1 else f"tobit/5/1/from-5-{first_v}")
    assert last == 30


def test_bible_unsplit_passage_cites_its_verse_range():
    # Even a passage holding a whole chapter is cited by its verses (1.4c, Carter
    # 4 Nov 2026), not as "Tobit 5".
    from ingest.bible import _join_with_verse_markers, _pieces
    verses = _verses(3, 100)
    (piece,) = _pieces("Tobit", 5, verses, _join_with_verse_markers(verses), "tobit/5/1")
    assert piece[1] == "Tobit 5:1–3" and piece[2] == "1"


def test_bible_verse_over_the_cap_gets_distinct_references():
    from ingest.bible import _join_with_verse_markers, _pieces
    verses = [(8, 12, "Short verse."), (8, 13, _sentences(random.Random(2), 4200))]
    pieces = _pieces("Esther", 8, verses, _join_with_verse_markers(verses), "esther/8/12")
    # The first piece holds 8:12 and the start of 8:13, the next the rest of 8:13.
    assert [ref for _, ref, *_ in pieces] == ["Esther 8:12–13", "Esther 8:13"]
    verses = [(8, 13, _sentences(random.Random(2), 8000))]
    refs = [ref for _, ref, *_ in _pieces("Esther", 8, verses, verses[0][2], "esther/8/13")]
    assert refs == [f"Esther 8:13 (part {k} of {len(refs)})" for k in range(1, len(refs) + 1)]
