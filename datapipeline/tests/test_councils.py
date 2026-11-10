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

from ingest import councils_deferrari as deferrari  # noqa: E402
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
                "Council of Vienne": 39, "Fourth Council of Constantinople": 27,
                "Fifth Lateran Council": 7}
# Schroeder's canons whose text Deferrari's replaces (1.2e-4).
REPLACED = {"Fourth Council of Constantinople": 5}
# Councils Schroeder prints in two series (Carter, 9 Nov 2026).
SERIES = {"First Council of Lyons": (18, 9), "Council of Vienne": (21, 18)}
EDITOR_WORDS = re.compile(r"\b(?:Comment|Summary)\.|Hefele|Mansi|Denzinger|DECREES OF THE COUNCILS")


def _schroeder(entry=SCHROEDER_ENTRY, **kw):
    return schroeder.build_schroeder(entry, "doc-id", "councils/ecum-09", **kw)


def _canons(doc):
    """The document's passages from Schroeder, without the texts Giles or Deferrari supply."""
    return [p for p in doc.passages if p.metadata["scan_id"] == "DisciplinaryCouncils"]


@pytest.mark.parametrize("council,count", CANON_COUNTS.items())
def test_schroeder_prints_every_canon_and_nothing_of_his_own(council, count):
    entry = {**SCHROEDER_ENTRY, "council": council}
    doc = _schroeder(entry)
    units = list(dict.fromkeys((p.chapter_key, p.unit_label) for p in _canons(doc)))
    count -= REPLACED.get(council, 0)
    series = SERIES.get(council, (count,))
    if council == "Fifth Lateran Council":      # a chapter per session
        series = (1, 1, 3, 2)
    assert [len([u for u in units if u[0] == key]) for key in dict.fromkeys(k for k, _ in units)] \
        == list(series)
    assert len(units) == count
    assert not [p.anchor for p in doc.passages if EDITOR_WORDS.search(p.content)]
    assert all(len(p.content) <= 4000 for p in doc.passages)


def _quotations_balance(text: str) -> bool:
    """Every “ is closed, where a quotation running over several paragraphs opens each
    of them with “ and closes only at its end (Vienne's quotation of Super cathedram)."""
    open_ = False
    for para in text.split("\n\n"):
        body = para
        if open_:
            if not para.startswith("“"):
                return False
            body = para[1:]
        depth = 1 if open_ else 0
        for ch in body:
            depth += {"“": 1, "”": -1}.get(ch, 0)
            if depth < 0:
                return False
        if depth > 1:
            return False
        open_ = depth == 1
    return not open_


def test_quotations_may_run_over_paragraphs():
    assert _quotations_balance("He said: “One.\n\n“Two.” Done.")
    assert not _quotations_balance("He said: “One.\n\nTwo.")
    assert not _quotations_balance("One.” Two.")


@pytest.mark.parametrize("work", [*schroeder.WORKS.values(),
                                  *(w for w, _ in deferrari.WORKS.values())])
def test_frozen_text_marks_balance_and_sentences_start_clean(work):
    # What a word-level comparison misses: a lost bracket or quotation mark, or a stop
    # read as a comma or a comma as a stop.
    for unit in read_text(work)["passages"]:
        text = unit["text"]
        assert text.count("(") == text.count(")"), unit["id"]
        assert _quotations_balance(text), unit["id"]
        assert text.count('"') % 2 == 0, unit["id"]          # Deferrari's are straight
        assert not re.search(r", But\b|\. (?:but|and|the)\b", text), unit["id"]


@pytest.mark.parametrize("council", CANON_COUNTS)
def test_every_word_of_the_frozen_text_reaches_a_passage(council):
    # The coverage check for these councils: the Tanner page is no longer their source.
    def words(text):
        return re.findall(r"\w+", text)
    doc = _schroeder({**SCHROEDER_ENTRY, "council": council})
    replaced = {"canon-" + s.replaces.rsplit("/", 1)[1]
                for s in deferrari.WORKS.get(council, ("", ()))[1] if s.replaces}
    frozen = [u for u in read_text(schroeder.WORKS[council])["passages"] if u["id"] not in replaced]
    assert words(" ".join(p.content for p in _canons(doc))) == \
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
                               for p in _canons(doc)))
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
        config = WorkConfig.load(work)
        assert (config.unit_count or len(config.unit_bounds)) == CANON_COUNTS[council]


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


# --- Giles's Matthew Paris for Lyons I (1.2e, Carter, 9 Nov 2026) ----------------------

from ingest import councils_giles as giles  # noqa: E402

LYONS_I = {**SCHROEDER_ENTRY, "council": "First Council of Lyons", "year": 1245}
BULL = "first-council-of-lyons/deposition"
LEGATE = "first-council-of-lyons/duty-of-the-legate"
GILES_NOTE = "Matthew Paris's version, in J. A. Giles's translation (1853)."
# Tanner's bull (G4, retired in 1.2e-2) and the Giles passage holding each part of it,
# matched by content since the two translations share no wording.
BULL_REDIRECTS = {
    "sec-2/5": "deposition", "sec-2/6": "deposition/from-p1-2", "sec-2/7": "deposition/from-p2",
    "sec-2/7/from-e24": "deposition/from-p2", "sec-2/7/from-e24-2": "deposition/from-p2",
    "sec-2/8": "deposition/from-p2-2", "sec-2/9": "deposition/from-p2-3",
    "sec-2/10": "deposition/from-p2-3", "sec-2/11": "deposition/from-p2-4",
    "sec-2/12": "deposition/from-p2-5"}


def _giles(doc):
    return [p for p in doc.passages if p.metadata["scan_id"] == "matthewparisseng02pari"]


def test_giles_texts_stand_before_and_after_the_canons_under_his_headings():
    doc = _schroeder(LYONS_I)
    chapters = list(dict.fromkeys((p.chapter_key, p.chapter_label) for p in doc.passages))
    assert chapters == [
        (BULL, "How the pope excommunicated the emperor Frederick at the council of Lyons"),
        ("first-council-of-lyons/series-1", "Canons, first series"),
        ("first-council-of-lyons/series-2", "Canons, second series"),
        (LEGATE, "Of the duty of the legate")]
    assert [p.position for p in doc.passages] == list(range(len(doc.passages)))
    assert doc.translation == "H. J. Schroeder (1937); J. A. Giles (1853)"
    assert _schroeder().translation == schroeder.TRANSLATION


def test_every_word_of_the_giles_text_reaches_a_passage_and_cuts_rejoin_unbroken():
    def words(text):
        return re.findall(r"\w+", text)
    passages = _giles(_schroeder(LYONS_I))
    frozen = read_text("giles-matthew-paris-lyons-1")
    assert words(" ".join(p.content for p in passages)) == \
        words(" ".join(u["text"] for u in frozen["passages"]))
    # One sentence runs over pp. 78-79; the clean-up's cut there is joined back.
    assert "through him. That the Church also wished" in passages[0].content
    assert not any(p.content.endswith(" St.") for p in passages)
    assert all(len(p.content) <= 4000 for p in passages)


def test_giles_frozen_text_passed_the_gate_and_carries_no_double_quotes():
    frozen = read_text("giles-matthew-paris-lyons-1")
    assert frozen["gate"] == "pass"
    for unit in frozen["passages"]:
        assert not re.search(r"[\"“”]", unit["text"]), unit["id"]
        assert unit["text"].count("(") == unit["text"].count(")"), unit["id"]


def test_giles_passages_carry_the_source_label_and_not_the_replaced_text_flag():
    for p in _giles(_schroeder(LYONS_I)):
        assert p.metadata["text_source"] == "ocr" and p.metadata["url"] == giles.SCAN_URL
        assert "text_replaced" not in p.metadata and p.metadata["pages"]


def test_a_closing_saint_moves_to_the_next_piece():
    assert giles._abbreviations_kept(["in the person of St.", "Peter, 'Whatever"]) == \
        ["in the person of", "St. Peter, 'Whatever"]


@pytest.mark.skipif(not _vendored, reason="needs the vendored manifest")
def test_every_giles_passage_carries_the_note_and_the_bull_its_date():
    notes = {p.anchor: p.note for p in _giles(_built("First Council of Lyons"))}
    assert set(notes) and all(n.startswith(GILES_NOTE) for n in notes.values())
    assert notes[BULL] == GILES_NOTE + " Matthew Paris dates the bull 16 July; " \
                                       "the council's acts give 17 July."
    assert notes[LEGATE] == GILES_NOTE


def test_tanners_bull_redirects_to_the_giles_passage_holding_each_part():
    reg = work_registry.load_registry()
    lyons = [r for r in reg.redirects if r.get("added_by") == "1.2e-3"]
    prefix = "first-council-of-lyons/"
    assert {r["old_anchor"].removeprefix(prefix): r["new_anchor"].removeprefix(prefix)
            for r in lyons} == BULL_REDIRECTS
    old = {r["old_passage_id"] for r in lyons}
    assert not [e for e in work_registry.open_removals(reg) if e.get("passage_id") in old]
    assert not [e for e in work_registry.open_removals(reg) if "(gap G4)" in e["detail"]]


# --- Constantinople IV and Lateran V, with Deferrari's texts (1.2e-4, Carter, 9 Nov 2026) --

CONSTANTINOPLE_IV = {**SCHROEDER_ENTRY, "council": "Fourth Council of Constantinople", "year": 870}
LATERAN_V = {**SCHROEDER_ENTRY, "council": "Fifth Lateran Council", "year": 1517}
DEFERRARI_SCAN = "sources-of-catholic-dogma-loreto-reprint"
SUMMARY_NOTE = "Summarised by Schroeder (1937); not the full text of this canon."
ANASTASIUS_NOTE = "From the Latin of Anastasius, in R. J. Deferrari's translation of Denzinger (1957)."
EXTRACT_NOTE = ("Extract, in R. J. Deferrari's translation of Denzinger, The Sources of Catholic "
                "Dogma (1957).")


def _units(doc):
    return list(dict.fromkeys(p.anchor.split("/from-")[0] for p in doc.passages))


def test_constantinople_iv_takes_deferraris_canons_and_keeps_schroeders_summary_of_17():
    doc = _schroeder(CONSTANTINOPLE_IV)
    slug = "fourth-council-of-constantinople"
    expected = [f"{slug}/canons/{n}" for n in range(1, 28)]
    expected.insert(17, f"{slug}/canons/17/extract")
    assert _units(doc) == expected
    by_unit = {p.anchor.split("/from-")[0]: p for p in doc.passages}
    deferrari_units = {f"{slug}/canons/{n}" for n in (1, 3, 11, 12, 21)} | {f"{slug}/canons/17/extract"}
    for unit, p in by_unit.items():
        assert p.metadata["scan_id"] == (DEFERRARI_SCAN if unit in deferrari_units else "DisciplinaryCouncils")
        assert p.chapter_label == "Canons"
    extract = by_unit[f"{slug}/canons/17/extract"]
    assert extract.unit_label == "Canon 17 (extract)" and extract.content.startswith("… Moreover")
    assert extract.metadata["text_replaced"] == deferrari.TEXT_REPLACED
    assert doc.translation == f"{schroeder.TRANSLATION}; {deferrari.TRANSLATION}"


def test_lateran_v_is_built_by_session_with_each_bull_under_its_latin_title():
    doc = _schroeder(LATERAN_V)
    slug = "fifth-lateran-council"
    assert _units(doc) == [f"{slug}/{u}" for u in (
        "session-8/apostolici-regiminis", "session-9/supernae-dispositionis-arbitrio",
        "session-10/inter-multiplices", "session-10/regimini-universalis-ecclesiae",
        "session-10/inter-sollicitudines", "session-11/supernae-majestatis-praesidio",
        "session-11/pastor-aeternus-gregem", "session-11/dum-intra-mentis-arcana")]
    first = doc.passages[0]
    assert (first.chapter_key, first.chapter_label, first.unit_label, first.reference) == (
        f"{slug}/session-8", "Session 8", "Apostolici regiminis",
        "Fifth Lateran Council, Session 8, Apostolici regiminis (part 1 of 2)")
    pastor = next(p for p in doc.passages if p.anchor.endswith("pastor-aeternus-gregem"))
    assert pastor.metadata["scan_id"] == DEFERRARI_SCAN and pastor.chapter_label == "Session 11"
    assert not [p.anchor for p in doc.passages if re.search(
        r"\b(?:second|third) part of (?:this|the) constitution\b|\bHefele\b|\bHardouin\b", p.content)]


@pytest.mark.parametrize("work", [w for w, _ in deferrari.WORKS.values()])
def test_deferrari_frozen_text_is_decree_text_only(work):
    for unit in read_text(work)["passages"]:
        text = unit["text"]
        assert not re.search(r"\b\d{3,4}[a-z]?\b", text), unit["id"]       # Denzinger's numbers
        assert not re.search(r"\[(?:see|cf\.)|\[[^\]]*\d+\s?:\s?\d+", text), unit["id"]
        assert not re.search(r"Anastasius:|\bCan\.\s*\d", text), unit["id"]


@pytest.mark.parametrize("council", ["Fourth Council of Constantinople", "Fifth Lateran Council"])
def test_every_word_of_deferraris_frozen_text_reaches_a_passage(council):
    def words(text):
        return re.findall(r"\w+", text)
    doc = _schroeder({**SCHROEDER_ENTRY, "council": council})
    work, _ = deferrari.WORKS[council]
    assert words(" ".join(p.content for p in doc.passages if p.metadata["scan_id"] == DEFERRARI_SCAN)) \
        == words(" ".join(u["text"] for u in read_text(work)["passages"]))


def test_deferrari_frozen_texts_passed_the_gate():
    for work, _ in deferrari.WORKS.values():
        assert read_text(work)["gate"] == "pass", work


@pytest.mark.skipif(not _vendored, reason="needs the vendored manifest")
def test_constantinople_iv_and_lateran_v_carry_their_notes_on_every_piece():
    for council in ("Fourth Council of Constantinople", "Fifth Lateran Council"):
        for p in _built(council).passages:
            unit = p.anchor.split("/from-")[0]
            if unit.endswith(("/canons/17/extract", "/pastor-aeternus-gregem")):
                expected = EXTRACT_NOTE
            elif p.metadata["scan_id"] == DEFERRARI_SCAN:
                expected = ANASTASIUS_NOTE
            elif council == "Fifth Lateran Council":
                expected = "Abridged in Schroeder (1937)."
            else:
                expected = SUMMARY_NOTE
            assert p.note == expected, p.anchor


def test_tanners_passages_go_where_their_text_went():
    reg = work_registry.current()
    open_ = {r["old_anchor"]: r["new_anchor"] for r in reg.redirects if not r.get("closed_by")}
    # Tanner's text of the part of canon 17 Deferrari prints, and of Pastor aeternus.
    assert open_["fourth-council-of-constantinople/sec-1/19"] == \
        "fourth-council-of-constantinople/canons/17/extract"
    assert open_["fifth-lateran-council/sec-0/58"] == "fifth-lateran-council/session-11/pastor-aeternus-gregem"
    rows = {r["live_anchor"]: r for r in reg.passages
            if r["document_id"] == "ef2654f7-1d3f-5dd0-b69b-ce0cb8626a61"}
    # The two live passages that are still one canon keep their IDs.
    assert rows["fourth-council-of-constantinople/sec-1/17"]["anchor"] == \
        "fourth-council-of-constantinople/canons/16"
    assert rows["fourth-council-of-constantinople/sec-1/18"]["anchor"] == \
        "fourth-council-of-constantinople/canons/17"
    # The credit line under the old `canon/1` retires, and no build reuses its anchor.
    assert rows["fourth-council-of-constantinople/canon/1"]["status"] == "retired"


def test_deferraris_edition_is_listed_on_both_councils_rows():
    rows = {r["work"]: r for r in rights_inventory.load()
            if r["source_path"] == "councils/DisciplinaryCouncils/"}
    for council in ("Fourth Council of Constantinople", "Fifth Lateran Council"):
        also, = rows[council]["also_from"]
        assert also["source_path"] == "councils/sources-of-catholic-dogma/"
        assert also["status"] == "pd-us-non-renewal" and also["translator"] == "Roy J. Deferrari"
