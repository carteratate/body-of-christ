import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
import defusedxml.ElementTree as ET
from ingest.common import (
    parse_thml_string, ThmlDocument,
    _detect_chunk_level, _detect_is_multi_author,
    _short_author_name, _maybe_title_case, _build_reference,
)

STANDARD_THML = """<?xml version="1.0" encoding="UTF-8"?>
<ThML>
  <ThML.head>
    <electronicEdInfo>
      <authorID>augustine</authorID>
      <bookID>confess</bookID>
    </electronicEdInfo>
    <DC>
      <DC.Title>The Confessions of Saint Augustine</DC.Title>
      <DC.Creator sub="Author" scheme="file-as">Augustine, Saint, Bishop of Hippo (345-430)</DC.Creator>
    </DC>
  </ThML.head>
  <ThML.body>
    <div1 title="Book I" n="i" id="bk1">
      <div2 title="Chapter I" n="i" id="bk1.ch1">
        <p id="p1">Great art Thou, O Lord, and greatly to be praised; great is Thy power, and Thy wisdom infinite. And Thee would man praise; man, but a particle of Thy creation.</p>
        <p id="p2">And Thee would man praise; he, but a particle of Thy creation. Thou awakest us to delight in Thy praise.</p>
      </div2>
      <div2 title="Chapter II" n="ii" id="bk1.ch2">
        <p id="p3">And how shall I call upon my God, my God and Lord, since, when I call for Him, I shall be calling Him to myself? and what room is there within me, whither my God can come into me?</p>
      </div2>
    </div1>
    <div1 title="Book II" n="ii" id="bk2">
      <div2 title="Chapter I" n="i" id="bk2.ch1">
        <p id="p4">I will now call to mind my past foulness, and the carnal corruptions of my soul; not because I love them, but that I may love Thee, O my God.</p>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""

SUMMA_THML = """<?xml version="1.0" encoding="UTF-8"?>
<ThML>
  <ThML.head>
    <electronicEdInfo>
      <authorID>aquinas</authorID>
      <bookID>summa</bookID>
    </electronicEdInfo>
    <DC>
      <DC.Title>Summa Theologica</DC.Title>
      <DC.Creator sub="Author" scheme="file-as">Thomas Aquinas, Saint (1225?-1274)</DC.Creator>
    </DC>
  </ThML.head>
  <ThML.body>
    <div1 title="First Part" n="i" id="FP">
      <div2 title="Treatise on Sacred Doctrine" n="i" id="FP.i">
        <div3 title="Question 1" n="i" id="FP_Q1">
          <div4 title="Article 1 - Whether sacred doctrine is necessary?" n="i" id="FP_Q1_A1">
            <p id="a1p1">Objection 1: It seems that it is not necessary.</p>
            <p id="a1p2">On the contrary, It is written: Instruction in every gracious art.</p>
            <p id="a1p3">I answer that, It was necessary for man salvation that there should be a knowledge revealed by God.</p>
            <p id="a1p4">Reply to Objection 1: Sciences are differentiated according to the various means through which knowledge is obtained.</p>
          </div4>
          <div4 title="Article 2 - Whether sacred doctrine is a science?" n="ii" id="FP_Q1_A2">
            <p id="a2p1">Objection 1: It seems that sacred doctrine is not a science.</p>
            <p id="a2p2">I answer that, Sacred doctrine is a science because it proceeds from principles established by the light of a higher science.</p>
          </div4>
        </div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""


def test_parse_thml_title():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.title == "The Confessions of Saint Augustine"

def test_parse_thml_author_cleaned():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.author == "Augustine, Saint, Bishop of Hippo"

def test_parse_thml_year_from_death():
    doc = parse_thml_string(STANDARD_THML)
    assert doc.year == 430

def test_parse_thml_standard_chunks_by_chapter():
    doc = parse_thml_string(STANDARD_THML)
    # New behavior: 3 chunks (Book I Ch I, Book I Ch II, Book II Ch I)
    assert len(doc.chunks) == 3


def test_parse_thml_reference_format():
    doc = parse_thml_string(STANDARD_THML)
    _, ref0, _, _ = doc.chunks[0]
    _, ref1, _, _ = doc.chunks[1]
    _, ref2, _, _ = doc.chunks[2]
    # New format: Author — Work, Book, Chapter
    assert ref0 == "Augustine — The Confessions of Saint Augustine, Book I, Chapter I"
    assert ref1 == "Augustine — The Confessions of Saint Augustine, Book I, Chapter II"
    assert ref2 == "Augustine — The Confessions of Saint Augustine, Book II, Chapter I"


def test_parse_thml_chapter_content_joined():
    doc = parse_thml_string(STANDARD_THML)
    content, _, _, _ = doc.chunks[0]
    assert "Great art Thou" in content
    assert "Thee would man praise" in content


def test_parse_thml_strips_xml_tags():
    thml = STANDARD_THML.replace('<p id="p1">', '<p id="p1"><i>Great</i> art Thou,')
    doc = parse_thml_string(thml)
    assert "<i>" not in doc.chunks[0][0]


def test_parse_thml_positions_sequential():
    doc = parse_thml_string(STANDARD_THML)
    positions = [c[2] for c in doc.chunks]
    assert positions == list(range(len(doc.chunks)))


def test_parse_thml_skips_short_chapters():
    short_thml = STANDARD_THML.replace(
        '<p id="p3">And how shall I call upon my God, my God and Lord, since, when I call for Him, I shall be calling Him to myself? and what room is there within me, whither my God can come into me?</p>',
        '<p id="p3">Short.</p>'
    )
    doc = parse_thml_string(short_thml)
    refs = [c[1] for c in doc.chunks]
    assert not any("Chapter II" in r and "Book I" in r for r in refs)

def test_parse_thml_summa_chunks_at_article():
    doc = parse_thml_string(SUMMA_THML)
    assert len(doc.chunks) == 2  # 2 articles


def test_parse_author_handles_approximate_dates():
    from ingest.common import _parse_author
    author, year = _parse_author("Athanasius, St. Archbishop of Alexandria (c.296-c.373)")
    assert year == 373
    assert "c.296" not in author
    assert "(c.296-c.373)" not in author

def test_chunk_standard_falls_back_to_div1_when_no_div2():
    from ingest.common import parse_thml_string
    doc = parse_thml_string(_INCARNATION_THML)
    assert len(doc.chunks) == 2
    _, ref0, _, _ = doc.chunks[0]
    _, ref1, _, _ = doc.chunks[1]
    assert "Chapter 1" in ref0 or "Chapter I" in ref0
    assert "Chapter 2" in ref1 or "Chapter II" in ref1
    assert "Word of God" in doc.chunks[0][0]


# ── Fixtures for depth-adaptive helpers ──────────────────────────────────────

_CITY_THML = """<?xml version="1.0"?>
<ThML>
  <ThML.head><DC><DC.Title>City of God</DC.Title>
  <DC.Creator sub="Author" scheme="file-as">Augustine, Saint (354-430)</DC.Creator></DC></ThML.head>
  <ThML.body>
    <div1 title="Volume I" n="i">
      <div2 title="Book I" shorttitle="Book I" n="i">
        <div3 title="Of the enemies of Christ" n="i"><p id="p1">When the barbarians sacked Rome, they spared all those who fled for refuge to the sanctuaries of the apostles and martyrs, and those who did not so flee were slain by the sword of the enemy.</p></div3>
        <div3 title="Of those who complain" n="ii"><p id="p2">But those who complain of Christian times seek the pleasures and abundance of this life, not the peace of eternity, yet since God gives rain upon the just and the unjust alike, they enjoy much that belongs to our faith.</p></div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""

_MULTI_AUTHOR_THML = """<?xml version="1.0"?>
<ThML>
  <ThML.head><DC><DC.Title>Apostolic Fathers</DC.Title>
  <DC.Creator sub="Author" scheme="file-as">Roberts, Alexander (1826-1901)</DC.Creator></DC></ThML.head>
  <ThML.body>
    <div1 title="CLEMENT OF ROME" n="i">
      <div2 title="First Epistle of Clement to the Corinthians" n="i">
        <div3 title="Chapter I. The salutation." n="i" shorttitle="Chapter I"><p id="p1">The Church of God which sojourns at Rome, to the Church of God sojourning at Corinth, to them that are called and sanctified by the will of God, through our Lord Jesus Christ: Grace unto you, and peace, from Almighty God through Jesus Christ, be multiplied.</p></div3>
      </div2>
    </div1>
    <div1 title="IGNATIUS OF ANTIOCH" n="ii">
      <div2 title="Epistle to the Ephesians" n="i">
        <div3 title="Chapter I. Praise of the Ephesians." n="i" shorttitle="Chapter I"><p id="p2">Ignatius, who is also Theophorus, to the Church which is at Ephesus in Asia, deservedly most happy, being blessed in the greatness and fulness of God the Father, and predestinated before the ages of time, that it should be always for an enduring and unchangeable glory.</p></div3>
      </div2>
    </div1>
  </ThML.body>
</ThML>"""

_INCARNATION_THML = """<?xml version="1.0"?>
<ThML>
  <ThML.head><DC><DC.Title>On the Incarnation</DC.Title>
  <DC.Creator sub="Author" scheme="file-as">Athanasius, Saint (c.296-c.373)</DC.Creator></DC></ThML.head>
  <ThML.body>
    <div1 title="Chapter 1. Creation and the Fall" type="chapter" n="i">
      <p id="p1">The Word of God, incorporeal and incorruptible and immaterial, came into our world to renew mankind and to drive out death, manifesting Himself through a body that we might receive some understanding of the invisible Father.</p>
    </div1>
    <div1 title="Chapter 2. The Divine Dilemma" type="chapter" n="ii">
      <p id="p2">For God had made man thus, and willed that he should abide in incorruption; but men, having turned from the contemplation of God to evil of their own devising, had come under sentence of death and corruption.</p>
    </div1>
  </ThML.body>
</ThML>"""


def _root(xml_str: str):
    xml_str = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml_str, flags=re.DOTALL)
    return ET.fromstring(xml_str)


def test_detect_chunk_level_confessions():
    assert _detect_chunk_level(_root(STANDARD_THML)) == 2


def test_detect_chunk_level_city_of_god():
    assert _detect_chunk_level(_root(_CITY_THML)) == 3


def test_detect_chunk_level_incarnation_special_case():
    assert _detect_chunk_level(_root(_INCARNATION_THML)) == 1


def test_detect_is_multi_author_single():
    assert _detect_is_multi_author(_root(STANDARD_THML)) is False


def test_detect_is_multi_author_multi():
    assert _detect_is_multi_author(_root(_MULTI_AUTHOR_THML)) is True


def test_short_author_name():
    assert _short_author_name("Augustine, Saint, Bishop of Hippo") == "Augustine"
    assert _short_author_name("Athanasius") == "Athanasius"


def test_maybe_title_case_allcaps():
    assert _maybe_title_case("CLEMENT OF ROME") == "Clement Of Rome"
    assert _maybe_title_case("Clement of Rome") == "Clement of Rome"


def test_parse_thml_confessions_generic_title_format():
    doc = parse_thml_string(STANDARD_THML)
    content, _, _, meta = doc.chunks[0]
    # Confessions: generic chapter titles → [Book I, Chapter I] breadcrumb format
    assert content.startswith("[Book I, Chapter I]")
    assert "Great art Thou" in content
    assert meta is not None
    assert meta["div_depth"] == 2


def test_parse_thml_city_of_god_depth_adaptive():
    doc = parse_thml_string(_CITY_THML)
    assert len(doc.chunks) == 2  # two div3 chapters
    content, ref, _, meta = doc.chunks[0]
    assert "Augustine — City of God, Book I" in ref
    assert meta["div_depth"] == 3
    # Content header: [Book I] chapter title (not generic)
    assert content.startswith("[Book I]")


def test_parse_thml_multi_author_reference():
    doc = parse_thml_string(_MULTI_AUTHOR_THML)
    _, ref0, _, _ = doc.chunks[0]
    assert ref0.startswith("Clement Of Rome")
    assert "First Epistle of Clement to the Corinthians" in ref0


def test_parse_thml_summa_reference_format():
    doc = parse_thml_string(SUMMA_THML)
    _, ref0, _, _ = doc.chunks[0]
    # Full breadcrumb: Part → Treatise → Question → Article
    assert "First Part" in ref0
    assert "Treatise on Sacred Doctrine" in ref0
    assert "Question 1" in ref0
    assert "Article 1" in ref0


def test_parse_thml_summa_article_content_complete():
    doc = parse_thml_string(SUMMA_THML)
    content, _, _, _ = doc.chunks[0]
    assert "Objection 1" in content
    assert "I answer that" in content
    assert "Reply to Objection" in content


def test_parse_thml_summa_metadata_populated():
    doc = parse_thml_string(SUMMA_THML)
    _, _, _, meta = doc.chunks[0]
    assert meta is not None
    assert meta["part"] == "First Part"
    assert meta["treatise"] == "Treatise on Sacred Doctrine"
    assert meta["question"] == "Question 1"
    assert "Article 1" in meta["article"]
    assert meta["div_depth"] == 4


# ---------------------------------------------------------------------------
# _split_at_whitespace — the fallback when no sentence boundary can be found.
#
# It carried two bugs at once, and the second hid the first: with overlap=0 it
# discarded everything after the first piece, and with overlap>0 it looped forever,
# so the only caller that would have exposed the truncation could never run.
# ---------------------------------------------------------------------------

import signal
import time

from ingest.common import _MIN_TAIL_CHARS, _split_at_whitespace, split_display_passage


def _words(text: str) -> list[str]:
    return text.split()


def test_display_passage_split_preserves_all_normalized_text():
    text = (
        "The first paragraph makes a complete claim.\n\n"
        + "The second paragraph develops that claim with several clauses; " * 90
        + "the final words remain present."
    )

    pieces = split_display_passage(text, max_chars=900)

    assert len(pieces) > 1
    assert [word for piece in pieces for word in _words(piece)] == _words(text)


def test_display_passage_split_balances_instead_of_emitting_a_runt():
    text = ("A long theological sentence with many connected words " * 75) + "8.21)."

    pieces = split_display_passage(text, max_chars=900)

    assert len(pieces) > 1
    assert min(map(len, pieces)) >= 450
    assert pieces[-1].endswith("8.21).")


def test_display_passage_split_prefers_a_nearby_sentence_boundary():
    first = "Grace perfects nature. " * 20
    second = "Charity orders every virtue toward God. " * 20
    text = first + second

    pieces = split_display_passage(text, max_chars=600)

    assert all(piece.endswith(".") for piece in pieces[:-1])
    assert [word for piece in pieces for word in _words(piece)] == _words(text)


def test_display_passage_split_recognizes_sentence_before_a_footnote():
    first = 'The council teaches this doctrine with authority."(28) '
    text = ("Supporting prose without a terminal mark " * 15) + first + (
        "Continuation without another terminal mark " * 30
    ) + "the passage finally ends."

    pieces = split_display_passage(text, max_chars=700)

    assert any(piece.endswith('authority."(28)') for piece in pieces[:-1])


def test_display_passage_does_not_treat_citation_period_as_sentence_end():
    citation = "as the psalm says, Ps. i. 1. even as the faithful have received it "
    text = ("Opening material without terminal punctuation " * 14) + citation + (
        "continued exposition without terminal punctuation " * 15
    ) + ". A genuinely new sentence begins here. " + ("Closing material " * 35)

    pieces = split_display_passage(text, max_chars=900)

    assert not any(piece.endswith("Ps. i. 1.") for piece in pieces[:-1])


def test_display_passage_does_not_split_paragraph_before_lowercase_continuation():
    false_break = "a citation interrupted by editorial material.\n\neven as the argument continues "
    text = ("Opening material without terminal punctuation " * 14) + false_break + (
        "continued exposition without terminal punctuation " * 15
    ) + ". A genuinely new paragraph begins here.\n\n" + ("Closing material " * 35)

    pieces = split_display_passage(text, max_chars=900)

    assert not any(piece.endswith("editorial material.") for piece in pieces[:-1])


def test_display_passage_does_not_treat_poetry_line_as_complete_paragraph():
    verse = "No outward sign to us is given,\n\nThe old complaint continues in this line "
    text = ("Opening material without terminal punctuation " * 14) + verse + (
        "continued exposition without terminal punctuation " * 8
    ) + ". A genuinely new paragraph begins here.\n\n" + ("Closing material " * 35)

    pieces = split_display_passage(text, max_chars=900)

    assert not any(piece.endswith("is given,") for piece in pieces[:-1])


def test_display_passage_split_falls_back_between_words():
    text = " ".join(f"word{i:04d}" for i in range(500))

    pieces = split_display_passage(text, max_chars=700)

    assert all(piece.split()[0].startswith("word") for piece in pieces)
    assert all(piece.split()[-1].startswith("word") for piece in pieces)
    assert [word for piece in pieces for word in _words(piece)] == _words(text)


def test_display_passage_split_leaves_naturally_short_text_alone():
    assert split_display_passage("Jesus wept.", max_chars=3500) == ["Jesus wept."]


def test_display_passage_split_is_linear_enough_for_large_source_units():
    text = "word " * 20_000

    started = time.perf_counter()
    pieces = split_display_passage(text, max_chars=3500)

    assert time.perf_counter() - started < 2
    assert [word for piece in pieces for word in piece.split()] == text.split()


def _within(seconds, fn, *args):
    """Run fn, failing loudly instead of hanging the suite.

    Restores the previous handler: installing one process-wide and leaving it there
    would let a later alarm from anything else surface as this assertion.
    """
    def _raise(signum, frame):
        raise AssertionError("did not terminate — the loop is not advancing")

    previous = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(seconds)
    try:
        return fn(*args)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def test_no_text_is_discarded_when_splitting_without_overlap():
    """Every ingest adapter calls this with overlap=0. Returning only the first piece
    silently dropped the tail of ~4,500 chunks across nine collections."""
    text = ("The Philosopher says that virtue is a habit. " * 120) + "FINAL CLAUSE."

    pieces = _split_at_whitespace(text, 3500, 0)

    assert len(pieces) > 1
    assert "FINAL CLAUSE." in pieces[-1]
    # Joined with the separator the split consumed, so a phrase cut at a boundary is
    # counted once rather than lost.
    assert " ".join(pieces).count("virtue is a habit") == 120


def test_splitting_with_overlap_terminates():
    """Once `end` reached the text's end, stepping back by the overlap moved `start`
    backwards and the same tail was re-emitted forever."""
    text = "word " * 800

    pieces = _within(2, _split_at_whitespace, text, 1800, 200)

    assert len(pieces) > 1


def test_overlap_repeats_context_between_pieces():
    """The overlap exists so a passage split mid-thought still carries its lead-in."""
    text = " ".join(f"w{i}" for i in range(2000))

    pieces = _split_at_whitespace(text, 1800, 200)

    assert pieces[1].split()[0] in pieces[0]


def test_text_within_the_budget_is_returned_whole():
    assert _split_at_whitespace("a short passage", 3500, 0) == ["a short passage"]


def _text_with_a_runt_tail():
    """Long enough to split, with the final word landing just past the cap.

    That is what leaves a runt: the whitespace scan looks ahead up to
    `_MAX_FALLBACK_SCAN`, so the first piece runs to the last space in the text and the
    remainder is a single short word.
    """
    body = "filler " * 507                       # ~3,549 chars
    return body[:3550].rstrip() + " tail."


def test_the_fold_threshold_stays_narrow_enough_to_bound_a_piece():
    """Folding is the only thing that can carry a piece past the cap, so the threshold
    is the width of that overshoot. Every value from 40 up removes all 57 catechism
    fragments equally, so a wider one buys nothing and costs bounded-ness: measured over
    the seven collections with local sources, 40 leaves 6 passages over 4,000 characters
    and 200 leaves 21."""
    assert _MIN_TAIL_CHARS <= 40


def test_a_runt_tail_is_folded_into_the_piece_before_it():
    """Splitting on a size budget can leave a fragment — the catechism produces a final
    piece reading only "irrelevant." — which alone gets its own embedding and can be
    retrieved as a result that tells the reader nothing."""
    text = _text_with_a_runt_tail()

    pieces = _split_at_whitespace(text, 3500, 0)

    assert len(pieces) == 1, f"runt emitted as its own piece: {pieces[-1]!r}"
    assert all(len(p) >= _MIN_TAIL_CHARS for p in pieces)


def test_folding_a_runt_keeps_its_text():
    """Folding must MERGE the fragment, not drop it — dropping would reintroduce the
    truncation this function was fixed to remove.

    Asserted on the merged piece rather than on the joined output: joining hides the
    difference, since a dropped tail and a folded one both leave the same text in
    `pieces[-1]` when there is only one piece to join.
    """
    text = _text_with_a_runt_tail()

    [merged] = _split_at_whitespace(text, 3500, 0)

    assert merged.endswith("tail.")
    assert len(merged) == len(text)
    assert merged.count("filler") == text.count("filler")


def test_an_overlapping_split_does_not_duplicate_text_within_a_piece():
    """Overlap repeats text ACROSS pieces by design; it must never repeat it INSIDE one.

    The `not overlap` guard in the fold is what prevents that, and it is currently
    unreachable: the sole overlapping caller uses 200, five times `_MIN_TAIL_CHARS`, and
    an overlapped tail is at least the overlap wide, so no input can produce a tail short
    enough to fold. This pins the property the guard protects rather than the guard, so
    it stays honest if either constant is retuned.
    """
    text = ("x" * 1900) + " " + ("z" * 199) + "     "

    pieces = _split_at_whitespace(text, 1800, 200)

    assert max(p.count("z") for p in pieces) <= text.count("z")


def test_a_non_positive_target_terminates():
    """`end` would never exceed `start`, so neither the step-back nor its fallback
    advances. The old guard caught this only as a side effect of the comparison that
    caused the truncation."""
    assert _within(2, _split_at_whitespace, "word " * 100, 0, 0)
    assert _within(2, _split_at_whitespace, "word " * 100, -5, 0)
