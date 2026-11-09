import os, sys, re
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup
from ingest.councils import build_ecumenical, build_vatican2, build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "councils")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))

CANON_HTML = """<html><body>
<h2>Canons</h2>
<p>Canon 1. If anyone says that the world was not created, let him be anathema and rejected.</p>
<p>Canon 2. If anyone denies the divine nature, let him be condemned by the holy synod here.</p>
</body></html>"""

VAT2_HTML = """<html><body>
<p><strong>CHAPTER I</strong></p>
<p>1. In His goodness and wisdom God chose to reveal Himself and to make known the mystery of His will.</p>
<p>2. By this revelation the invisible God out of the abundance of His love speaks to men as friends.</p>
</body></html>"""


def test_ecumenical_canon_passages_have_unit_and_anchor():
    entry = {"council": "Council of Trent", "document": "Council of Trent", "year": 1563,
             "group": "ecumenical-1-20", "file": "x.html", "url": "http://example"}
    passages = build_ecumenical(entry, BeautifulSoup(CANON_HTML, "lxml")).passages
    assert [p.unit_label for p in passages] == ["Canon 1", "Canon 2"]
    assert passages[0].anchor.startswith("council-of-trent/canon/1")
    assert not passages[0].content.lstrip().startswith("[")


def test_vatican2_numbered_paragraphs_under_chapter():
    entry = {"council": "Second Vatican Council", "document": "Dei Verbum",
             "document_type": "constitution", "year": 1965, "group": "vatican-ii",
             "file": "x.html", "url": "http://example"}
    d = build_vatican2(entry, BeautifulSoup(VAT2_HTML, "lxml"))
    assert d.title == "Dei Verbum"
    assert d.metadata["council"] == "Second Vatican Council"
    assert [p.unit_label for p in d.passages] == ["§1", "§2"]
    assert any("Chapter" in p.chapter_label for p in d.passages)


# Bug 1+4: chapters marked with <b>, a trailing table-of-contents copy, and a
# <p><b> double-hit must all be handled — content split onto the real chapters,
# trailing TOC ignored, no phantom/duplicated chapters.
VAT2_BOLD_HTML = """<html><body>
<p><b>CHAPTER I</b></p>
<p>1. In His goodness God chose to reveal Himself and to make known the mystery of His will to men.</p>
<p>2. By this revelation the invisible God speaks to men as friends and lives among them in friendship.</p>
<b>CHAPTER II</b>
<p>3. In His gracious goodness God has seen to it that what He had revealed for salvation would abide.</p>
<p>Chapter I</p>
<p>Chapter II</p>
</body></html>"""


def test_vatican2_detects_bold_chapters_ignores_trailing_toc():
    entry = {"council": "Second Vatican Council", "document": "Dei Verbum",
             "document_type": "constitution", "year": 1965, "group": "vatican-ii",
             "file": "x.html", "url": "http://example"}
    d = build_vatican2(entry, BeautifulSoup(VAT2_BOLD_HTML, "lxml"))
    labels = [p.chapter_label for p in d.passages]
    assert [p.unit_label for p in d.passages] == ["§1", "§2", "§3"]
    # §1,§2 under Chapter I; §3 under Chapter II — two distinct real chapters.
    assert labels[0] == labels[1] == "Chapter I"
    assert labels[2] == "Chapter II"
    # exactly two chapters (no phantom from the <p><b> double-hit or trailing TOC)
    assert len({p.chapter_key for p in d.passages}) == 2


VAT2_FLAT_HTML = """<html><body>
""" + "\n".join(
    f"<p>{i}. This is numbered paragraph {i} of a declaration with no chapter headings at all here.</p>"
    for i in range(1, 26)
) + """
</body></html>"""


def test_vatican2_headerless_falls_back_to_paragraph_buckets():
    entry = {"council": "Second Vatican Council", "document": "Dignitatis Humanae",
             "document_type": "declaration", "year": 1965, "group": "vatican-ii",
             "file": "x.html", "url": "http://example"}
    d = build_vatican2(entry, BeautifulSoup(VAT2_FLAT_HTML, "lxml"))
    assert len(d.passages) == 25
    labels = {p.chapter_label for p in d.passages}
    # 25 paragraphs in buckets of 20 → "Paragraphs 1–20" and "Paragraphs 21–40"
    assert labels == {"Paragraphs 1–20", "Paragraphs 21–40"}
    assert all(p.anchor and p.chapter_key for p in d.passages)


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_all_documents_build_and_are_clean():
    docs = build_documents()
    assert len(docs) == 36          # 20 ecumenical + 16 Vatican II
    for d in docs:
        assert d.passages, d.title
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not p.content.lstrip().startswith("[")
            assert not re.search(r"\[\d+\]", p.content)


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_document_ids_unique():
    ids = [d.id for d in build_documents()]
    assert len(ids) == len(set(ids))


# --- Councils from Schroeder (1.2e) ---------------------------------------------------

from ingest import councils_schroeder as schroeder  # noqa: E402
from ocr.fixes import read_text  # noqa: E402
from ocr.work import WorkConfig  # noqa: E402
import registry as work_registry  # noqa: E402
import rights_inventory  # noqa: E402

SCHROEDER_ENTRY = {"council": "First Lateran Council", "year": 1123, "council_number": 9,
                   "url": "https://www.papalencyclicals.net/councils/ecum09.htm"}
CANON_COUNTS = {"First Lateran Council": 22, "Second Lateran Council": 30,
                "Third Lateran Council": 27, "Fourth Lateran Council": 71,
                "First Council of Lyons": 27, "Second Council of Lyons": 32,
                "Council of Vienne": 39}
# Councils Schroeder prints in two series (Carter, 9 Nov 2026).
SERIES = {"First Council of Lyons": (18, 9), "Council of Vienne": (21, 18)}
EDITOR_WORDS = re.compile(r"\b(?:Comment|Summary)\.|Hefele|Mansi|Denzinger|DECREES OF THE COUNCILS")


def _schroeder(entry=SCHROEDER_ENTRY, **kw):
    return schroeder.build_schroeder(entry, "doc-id", "councils/ecum-09", **kw)


@pytest.mark.parametrize("council,count", CANON_COUNTS.items())
def test_schroeder_prints_every_canon_and_nothing_of_his_own(council, count):
    entry = {**SCHROEDER_ENTRY, "council": council}
    doc = _schroeder(entry)
    units = list(dict.fromkeys((p.chapter_key, p.unit_label) for p in doc.passages))
    series = SERIES.get(council, (count,))
    assert [len([u for u in units if u[0] == key]) for key in dict.fromkeys(k for k, _ in units)] \
        == list(series)
    assert len(units) == count
    assert not [p.anchor for p in doc.passages if EDITOR_WORDS.search(p.content)]
    assert all(len(p.content) <= 4000 for p in doc.passages)


@pytest.mark.parametrize("work", schroeder.WORKS.values())
def test_frozen_text_marks_balance_and_sentences_start_clean(work):
    # What a word-level comparison misses: a lost bracket or quotation mark, or a stop
    # read as a comma or a comma as a stop.
    for unit in read_text(work)["passages"]:
        text = unit["text"]
        assert text.count("(") == text.count(")"), unit["id"]
        assert text.count("“") == text.count("”"), unit["id"]
        assert not re.search(r", But\b|\. (?:but|and|the)\b", text), unit["id"]


@pytest.mark.parametrize("council", CANON_COUNTS)
def test_every_word_of_the_frozen_text_reaches_a_passage(council):
    # The coverage check for these councils: the Tanner page is no longer their source.
    def words(text):
        return re.findall(r"\w+", text)
    doc = _schroeder({**SCHROEDER_ENTRY, "council": council})
    frozen = read_text(schroeder.WORKS[council])["passages"]
    assert words(" ".join(p.content for p in doc.passages)) == \
        words(" ".join(u["text"] for u in frozen))


def test_frozen_texts_passed_the_gate():
    for council, work in schroeder.WORKS.items():
        assert council in schroeder.HELD or read_text(work)["gate"] == "pass", council


def test_schroeder_document_keeps_the_gap_link_and_points_at_the_scan():
    doc = _schroeder()
    assert doc.metadata["held_text_url"] == SCHROEDER_ENTRY["url"]
    assert doc.metadata["url"] == schroeder.SCAN_URL
    assert doc.translation == schroeder.TRANSLATION


def test_schroeder_passages_carry_the_source_label_and_declare_the_new_text():
    for p in _schroeder().passages:
        assert p.metadata["text_source"] == "ocr"
        assert p.metadata["scan_id"] == "DisciplinaryCouncils"
        assert p.metadata["text_replaced"] == schroeder.TEXT_REPLACED
        assert p.metadata["pages"]


def test_schroeder_anchors_are_canon_numbers_in_his_order():
    doc = _schroeder()
    assert [p.anchor for p in doc.passages] == \
        [f"first-lateran-council/canon/{n}" for n in range(1, 23)]
    assert [p.position for p in doc.passages] == list(range(22))


def test_a_council_in_two_series_names_both():
    doc = _schroeder({**SCHROEDER_ENTRY, "council": "First Council of Lyons"})
    units = list(dict.fromkeys((p.anchor.split("/from-")[0], p.chapter_key, p.chapter_label)
                               for p in doc.passages))
    assert units[0] == ("first-council-of-lyons/series-1/canon/1",
                        "first-council-of-lyons/series-1", "Canons, first series")
    assert units[18] == ("first-council-of-lyons/series-2/canon/1",
                         "first-council-of-lyons/series-2", "Canons, second series")
    assert [u[0] for u in units] == [f"first-council-of-lyons/series-{s}/canon/{n}"
                                     for s, k in ((1, 18), (2, 9)) for n in range(1, k + 1)]
    second = next(p for p in doc.passages if p.anchor == "first-council-of-lyons/series-2/canon/4")
    assert second.reference == "First Council of Lyons, Second series, Canon 4"


def test_a_held_council_emits_no_passages_and_keeps_its_document():
    doc = _schroeder(held=frozenset({"First Lateran Council"}))
    assert doc.id == "doc-id" and doc.passages == []


def _built(council):
    doc = next(d for d in build_documents() if d.title == council)
    return work_registry.apply_overrides(doc)


@pytest.mark.skipif(not _vendored, reason="needs the vendored manifest")
def test_other_recension_note_sits_on_schroeders_13_and_17():
    # Tanner's canons 15 and 16 are Schroeder's 13 and 17 (inventory, Lateran I).
    noted = {p.anchor: p.note for p in _built("First Lateran Council").passages if p.note}
    assert noted == {
        "first-lateran-council/canon/13": "Translated from another recension of this canon.",
        "first-lateran-council/canon/17": "Translated from another recension of this canon."}


@pytest.mark.skipif(not _vendored, reason="needs the vendored manifest")
def test_schroeder_councils_route_through_their_frozen_document_ids():
    docs = {d.title: d for d in build_documents()}
    rows = rights_inventory.by_document_id(rights_inventory.load())
    for council in schroeder.WORKS:
        row = rows[docs[council].id]
        assert row["status"] == "pd-us-non-renewal" and row["planned_for"] is None
        assert row["source_path"] == "councils/DisciplinaryCouncils/"


def test_every_work_config_matches_its_canon_count():
    for council, work in schroeder.WORKS.items():
        assert WorkConfig.load(work).unit_count == CANON_COUNTS[council]


@pytest.mark.skipif(not _vendored, reason="needs the vendored manifest")
@pytest.mark.parametrize("council,unit", [
    ("Council of Vienne", "council-of-vienne/series-1/canon/21"),     # Exivi de paradiso
    ("Second Council of Lyons", "second-council-of-lyons/canon/32"),  # Zelus fidei
])
def test_abridged_texts_carry_their_note_on_every_piece(council, unit):
    # Schroeder's condensed texts are published with a note on each passage (Carter,
    # 4 Nov 2026).
    passages = _built(council).passages
    noted = {p.anchor for p in passages if p.note == "Abridged in Schroeder (1937)."}
    assert noted == {p.anchor for p in passages if p.anchor.split("/from-")[0] == unit}
