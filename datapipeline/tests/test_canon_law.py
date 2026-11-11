import sys, os

# Set required env vars before importing ingest.canon_law, which imports config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re

import pytest

from ingest.canon_law import (
    CanonText, Heading, _book_for, _respell, _spelling, amending_act, build_documents,
    choose_current, deduplicate_urls, history_year, parse_canon_page, read_pages,
)
from ingest.canon_overrides import NO_ENGLISH
from registry import history_problems

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "canon-law")
_vendored = os.path.exists(os.path.join(_SRC, "pages.json"))

_MARK = '<font color="#663300" size="3"><b><i>n</i></b></font>'
_LEGEND = f'<p><i>({_MARK}: indicates that the text corresponds to a new version or a new paragraph)</i></p>'
_ACT = ('<a href="https://www.vatican.va/content/francesco/en/motu_proprio/documents/'
        'x.html">Apostolic Letter issued “Motu proprio” Competentias quasdam decernere</a>')


def _page(body: str) -> str:
    return f"<html><body><table><tbody><tr><td>{body}</td></tr></tbody></table></body></html>"


def _texts(body: str) -> list[CanonText]:
    return parse_canon_page(_page(body))[0]


def _current(body: str) -> dict[int, CanonText]:
    return choose_current(_texts(body))[0]


SAMPLE = _page("""
<p align="center"><b>CODE OF CANON LAW</b></p>
<p>Can. 1 The canons of this Code regard only the Latin Church.</p>
<p>Can. 5 §1. Universal or particular customs presently in force which are contrary.</p>
<p>§2. Universal or particular customs beyond the law are preserved.</p>
<p>Can. 6 §1. When this Code takes force, the following are abrogated:</p>
<p>1/ the Code of Canon Law promulgated in 1917;</p>
""")


def test_parse_canon_page_extracts_canons_without_prefix():
    canons, _ = parse_canon_page(SAMPLE)
    assert [c.number for c in canons] == [1, 5, 6]
    assert canons[0].content == "The canons of this Code regard only the Latin Church."
    assert "§2." in canons[1].content and "1/" in canons[2].content
    assert not any("CODE OF CANON LAW" in c.content for c in canons)


def test_canon_glued_after_br_is_split():
    canons = _current("""
<p>Can. 237 §1. Where it is possible, there is to be a major seminary.</p>
<p>§2. An interdiocesan seminary is not to be erected.<br>
<br>
Can. 238 §1. Seminaries legitimately erected possess juridic personality.</p>
<p>§2. In the handling of all affairs, the rector represents it.</p>""")
    assert sorted(canons) == [237, 238]
    assert "Can." not in canons[237].content
    assert canons[237].content.endswith("is not to be erected.")
    assert canons[238].content.startswith("§1. Seminaries")
    assert "§2. In the handling" in canons[238].content


def test_marker_before_can_is_recognised():
    canons = _current(f"""
<p>{_MARK} Can. 265 Every cleric must be incardinated, or also in a public clerical association.<br>
<br>
Can. 266 §1. Through the reception of the diaconate, a person becomes a cleric.</p>""")
    assert canons[265].marked and canons[265].content.startswith("Every cleric")
    assert canons[266].content.startswith("§1. Through the reception of the diaconate")
    assert not canons[266].marked


def test_marker_inside_text_is_removed():
    canons = _current(f"""
<p>Can. 688 §1. A person who wishes to leave can depart.</p>
<p><i><b>{_MARK}</b></i>§2. During the time of temporary profession, a person can obtain an indult.</p>""")
    assert canons[688].marked
    assert "n§" not in canons[688].content and "\n§2. During" in canons[688].content


def test_earlier_version_block_is_not_current():
    canons = _current(f"""
<p>{_MARK} Can. 1308 §1. A reduction of Masses is reserved to the diocesan bishop.</p>
<p>Can. 1309 To the same authorities belongs the power to transfer obligations.</p>
<p>_______________________</p>
{_LEGEND}
<p>Cf. {_ACT} (11 February 2022)</p>
<p>[Earlier version]</p>
<p>Can. 1308 §1. A reduction of Masses is reserved to the Apostolic See.</p>""")
    assert "diocesan bishop" in canons[1308].content
    assert "Apostolic See" not in canons[1308].content
    assert "Cf." not in canons[1309].content and "indicates" not in canons[1309].content


def test_earlier_version_becomes_unsearchable_history_passage():
    texts = _texts(f"""
<p>{_MARK} Can. 686 §1. Not for more than five years.</p>
<p>Can. 687 An exclaustrated member is freed.</p>
<p>__________________________</p>
{_LEGEND}
<p>[ <i>Original version</i> ]</p>
<p>Can. 686 §1. Not for more than three years.</p>
<p>§2. It is only for the Apostolic See to grant an indult for nuns.</p>""")
    current, history = choose_current(texts)
    assert [h.number for h in history] == [686]
    old = history[0]
    assert old.content == ("§1. Not for more than three years.\n"
                           "§2. It is only for the Apostolic See to grant an indult for nuns.")
    assert history_year(old, current[686]) == 1983


def test_marked_superseded_text_takes_its_act_year():
    texts = _texts(f"""
<p>Can. 700 {_MARK} <a href="https://www.vatican.va/a.html">Apostolic Letter issued “Motu Proprio”
modifying the terms of recourse (2 April 2023) | Francis</a>: In canon 700 the term is replaced,
the canon being formulated as follows:</p>
<p><i>«Decretum dimissionis vim habet. Recursus effectum habet suspensivum».</i></p>
<p>Can. 701 By legitimate dismissal, vows cease.</p>
<p>__________________________</p>
{_LEGEND}
<p>[Original version]</p>
<p>Can. 699 §2. In the autonomous monasteries it belongs to the diocesan bishop.</p>
<p>Can. 700{_MARK}: A decree of dismissal must indicate recourse within ten days.</p>
<p>Cf. {_ACT} (11 February 2022)</p>
<p>[Original version]</p>
<p>Can. 700 A decree of dismissal does not have effect unless confirmed.</p>""")
    current, history = choose_current(texts)
    assert current[700].content == ("Decretum dimissionis vim habet. "
                                   "Recursus effectum habet suspensivum.")
    assert current[700].cut and current[700].cut[0].startswith("Apostolic Letter issued")
    assert amending_act(current[700]).year == 2023
    years = sorted(history_year(h, current[700]) for h in history if h.number == 700)
    assert years == [1983, 2022]


def test_bold_canon_outside_p_is_found():
    canons = _current("""
<p>Can. 1329 §1. Where a number of persons conspire together.</p>
<b>Can. 1330</b>&#8212;&nbsp;An offence which consists in a declaration is not effected
if no one perceives it. <p>&nbsp;</p>
<p align="center">TITLE IV.</p>
<p><b>Can. 1331</b>&#8212;&nbsp;§ 1. An excommunicated person is prohibited:</p>""")
    assert sorted(canons) == [1329, 1330, 1331]
    assert canons[1330].content.startswith("An offence which consists")


def test_footer_legend_is_cut():
    canons, notes = parse_canon_page(_page(f"""
<p>Can. 123 Upon the extinction of a public juridic person, its goods go to the superior.</p>
<hr />
<p> ({_MARK}: indicates that the text corresponds to a new version or a new paragraph)<br>
<br>
For Can. 111 and Can. 112: Cf. cf: {_ACT} (31 May 2016)</p>"""))
    assert canons[0].content.endswith("go to the superior.")
    assert any(n.startswith("For Can. 111") for n in notes)


def test_rule_line_note_is_cut_and_body_resumes_at_heading():
    canons = _current("""
<p>Can. 297 The statutes likewise are to define the relations of the prelature.</p>
<p>__________________________________________</p>
<p>Apostolic Letter issued “Motu Proprio” modifying Canons 295-296, 8 August 2023</p>
<p>TITLE V. ASSOCIATIONS OF THE CHRISTIAN FAITHFUL</p>
<p>Can. 298 §1. In the Church there are associations.</p>""")
    assert canons[297].content.endswith("relations of the prelature.")
    assert canons[298].content == "§1. In the Church there are associations."


def test_book_vi_leading_dash_removed():
    canons = _current("<p><b>Can. 1311</b>&#8212;&nbsp;§ 1. The Church has its own right.</p>")
    assert canons[1311].content == "§ 1. The Church has its own right."


def test_amended_flag_set_from_marker():
    canons = _current(f"""
<p>Can. 774 §1. The care for catechesis is incumbent on all.</p>
<p>Can. 775 §1. The diocesan bishop is to issue norms.</p>
<p>{_MARK}§2. It is for the conference of bishops to issue catechisms.</p>""")
    assert canons[775].marked and not canons[774].marked


def test_act_reference_in_canon_is_cut():
    canons = _current("""
<p>Can. 230 §1. Lay persons can be admitted to the ministries of lector and acolyte.
[Cf. <a href="https://www.vatican.va/l.html"><i>Letter of the Holy Father</i> (10 January 2021)</a>]</p>
<p>§2. That institute is called clerical which is under the direction of clerics (Cf.
<a href="https://press.vatican.va/r.html">Rescriptum ex Audientia Ss.mi</a>, 18 May 2022 &#8211;
Congregation), assumes the exercise of sacred orders.</p>""")
    text = canons[230].content
    assert "Cf." not in text and "Rescriptum" not in text and "[" not in text
    assert "acolyte.\n§2." in text and "of clerics, assumes" in text
    assert len(canons[230].cut) == 2


def test_two_unmarked_current_texts_raise():
    with pytest.raises(ValueError, match="printed twice"):
        _current("<p>Can. 5 One.</p><p>Can. 5 Two.</p>")


def test_heading_path_from_index_resets_lower_levels():
    title = Heading("TITLE", "I", "Baptism")
    chapter = Heading("CHAPTER", "V", "Proof")
    toc = [(None, Heading("PART", "I", "The Sacraments")), ("TITLE_I", title),
           ("CHAPTER_V", chapter), ("TITLE_II", Heading("TITLE", "II", "Confirmation"))]
    canons, _ = parse_canon_page(_page("""
<p><a name="TITLE_I.">TITLE I. BAPTISM</a></p>
<p>Can. 849 Baptism is the gate.</p>
<p><a name="CHAPTER_V.">CHAPTER V.</a></p>
<p>Can. 877 The pastor must record.</p>
<p><a name="TITLE_II.">TITLE II.</a></p>
<p>Can. 879 The sacrament of confirmation.</p>"""), toc=toc)
    paths = {c.number: [h.label for h in c.path] for c in canons}
    assert paths[849] == ["Part I: The Sacraments", "Title I: Baptism"]
    assert paths[877] == ["Part I: The Sacraments", "Title I: Baptism", "Chapter V: Proof"]
    assert paths[879] == ["Part I: The Sacraments", "Title II: Confirmation"]


def test_heading_after_note_and_unanchored_entries_open_in_place():
    toc = [("PART_II", Heading("PART", "II", "Hierarchy")),
           ("SECTION_II", Heading("SECTION", "II", "Particular Churches")),
           (None, Heading("TITLE", "I", "Particular Churches")),
           ("CHAPTER_II", Heading("CHAPTER", "II", "Bishops")),
           ("Art._1", Heading("ARTICLE", "1", "Bishops in General")),
           ("TITLE_V", Heading("TITLE", "V", "Associations"))]
    canons, _ = parse_canon_page(_page("""
<p><a name="PART_II">PART II.</a></p>
<p><a name="SECTION_II">SECTION II.</a></p>
<p>Can. 368 Particular churches are dioceses.</p>
<p><a name="CHAPTER_II.">CHAPTER II.</a></p>
<p><a name="Art._1.">Art. 1.</a></p>
<p>Can. 375 Bishops are pastors.</p>
<p>____________________</p>
<p>Apostolic Letter issued modifying Canons 295-296, 8 August 2023</p>
<p><a name="TITLE_V.">TITLE V.</a></p>
<p>Can. 298 In the Church there are associations.</p>"""), toc=toc)
    paths = {c.number: [h.level for h in c.path] for c in canons}
    assert paths[368] == ["PART", "SECTION", "TITLE"]
    assert paths[375] == ["PART", "SECTION", "TITLE", "CHAPTER", "ARTICLE"]
    assert paths[298] == ["PART", "SECTION", "TITLE"]
    assert canons[-1].path[-1].title == "Associations"
    assert not any("Art." in c.content for c in canons)


def test_spelling_corrections_apply_only_to_listed_canons():
    fixes = {253: [("diVerent", "different")]}
    assert _respell(253, "that diVerent teachers", fixes) == "that different teachers"
    assert _respell(254, "that diVerent teachers", fixes) == "that diVerent teachers"
    with pytest.raises(ValueError):
        _respell(253, "no such word", fixes)


def test_spelling_list_is_reviewed_words_only():
    rows = [r for rs in _spelling().values() for r in rs]
    assert rows
    for broken, corrected in rows:
        assert re.search(r"[VY]", broken) and not re.search(r"[VY]", corrected)
        assert broken.replace("V", "ff").replace("Y", "ffi") == corrected


def test_deduplicate_urls_strips_fragments():
    urls = [
        "/archive/cic_lib1-cann1-6_en.html",
        "/archive/cic_lib1-cann1-6_en.html#Art._1.",
        "/archive/cic_lib1-cann7-22_en.html",
    ]
    result = deduplicate_urls(urls, base="http://www.vatican.va")
    assert result == ["http://www.vatican.va/archive/cic_lib1-cann1-6_en.html",
                      "http://www.vatican.va/archive/cic_lib1-cann7-22_en.html"]


def test_book_for_assigns_by_canon_range():
    assert _book_for(1).startswith("Book I")
    assert _book_for(203).startswith("Book I")
    assert _book_for(204).startswith("Book II")
    assert _book_for(750).startswith("Book III")
    assert _book_for(1752).startswith("Book VII")


# ── Vendored source ─────────────────────────────────────────────────────────

vendored = pytest.mark.skipif(not _vendored, reason="canon-law not vendored")


@pytest.fixture(scope="module")
def doc():
    return build_documents()[0]


@pytest.fixture(scope="module")
def canons(doc):
    return {p.metadata["canon"]: p for p in doc.passages if p.searchable}


@vendored
def test_canon_numbers_are_exactly_1_to_1752(doc, canons):
    current = [p.metadata["canon"] for p in doc.passages if p.superseded_by_anchor is None]
    # Less the canons rule E retires (1.5b, tests/test_canon_overrides.py).
    assert sorted(current) == [n for n in range(1, 1753) if n not in NO_ENGLISH]
    assert all(p.anchor == f"can/{n}" for n, p in canons.items())
    assert [p.position for p in doc.passages] == list(range(len(doc.passages)))


@vendored
def test_superseded_text_is_not_current(canons):
    assert "five years" in canons[686].content.split("\n")[0]
    assert "public clerical association" in canons[265].content
    assert canons[266].content.startswith("§1. Through the reception of the diaconate")
    assert "diocesan bishop" in canons[1308].content.split("\n")[0]
    assert "Apostolic See" not in canons[1308].content.split("\n")[0]
    assert "Apostolic See" not in canons[1310].content.split("\n")[0]
    for n in (112, 238, 689, 1330):
        assert canons[n].content


@vendored
def test_history_passages(doc):
    history = [p for p in doc.passages if p.superseded_by_anchor]
    assert history and not history_problems(doc)
    by = {p.anchor: p for p in history}
    assert "three years" in by["can/686/history-1983"].content
    assert "Apostolic See" in by["can/1308/history-1983"].content.split("\n")[0]
    # A canon rule E retires keeps no history (1.5b): c. 700's two earlier texts are gone.
    assert not [a for a in by if int(a.split("/")[1]) in NO_ENGLISH]
    for p in history:
        assert not p.searchable
        assert re.fullmatch(r"can/\d+/history-\d{4}", p.anchor)
        n = p.metadata["canon"]
        assert p.reference == f"Code of Canon Law, Can. {n} (text in force from {p.anchor[-4:]})"


@vendored
def test_no_footer_marker_or_note_debris(doc):
    for p in doc.passages:
        text = p.content
        for bad in ("Earlier version", "Original version", "indicates that", "For Can.",
                    "Apostolic Letter issued", "Indica che", "____"):
            assert bad not in text, (p.anchor, bad)
        assert not re.match(r"^n(?:§|[A-Z])", text), p.anchor
        assert not text.startswith("—"), p.anchor
        assert "n§" not in text, p.anchor
        assert not re.search(r"[a-z,]\n[a-z(]", text), p.anchor
        assert not re.search(r"(^|\n)(Art\.|ART\.|[A-Z]{3,}( [A-Z,]{2,})+)", text), p.anchor


@vendored
def test_amended_list_equals_marker_list(canons):
    texts, _ = read_pages()
    current, _ = choose_current(texts)
    marked = sorted(n for n, t in current.items() if t.marked)
    amended = sorted(n for n, p in canons.items() if p.metadata.get("amended"))
    # 1.5b: the canons rule E retires have no passage, and the De concordia marriage
    # canons, which the page prints unmarked in their 1983 English, are amended.
    marriage = {1108, 1109, 1111, 1112, 1116, 1127}
    assert amended == sorted((set(marked) - set(NO_ENGLISH)) | marriage)
    assert len(marked) == 27


@vendored
def test_heading_paths_follow_the_index(canons):
    def path(n):
        return canons[n].chapter_label
    assert path(849).endswith("Part I: The Sacraments — Title I: Baptism")
    assert "Part II: The Other Acts of Divine Worship — Title I: Sacramentals" in path(1166)
    assert "Part III: Sacred Places and Times — Title I: Sacred Places" in path(1205)
    assert canons[849].chapter_key != canons[1166].chapter_key != canons[1205].chapter_key
    assert path(265).endswith("Chapter II: The Enrollment, or Incardination, of Clerics")
    assert "Title V: Associations of the Christian Faithful" in path(298)
    assert "Section II" in path(431) and "Title I: Particular Churches" in path(368)
    assert path(157).endswith("Article 1: Free Conferral")
    assert "Chapter II" in path(1481) and "Chapter I:" not in path(1481)
    keys = [p.chapter_key for p in sorted(canons.values(), key=lambda p: p.position)]
    runs = [k for i, k in enumerate(keys) if i == 0 or keys[i - 1] != k]
    assert len(runs) == len(set(runs)), "a chapter key covers two separate runs"


@vendored
def test_no_ligature_corruption(doc):
    from checks.content import LIGATURE_CORRUPTION
    assert not [p.anchor for p in doc.passages if LIGATURE_CORRUPTION.search(p.content)]


@vendored
def test_exactly_seven_books_no_latin_labels(doc):
    books = {p.metadata["book"] for p in doc.passages}
    assert len(books) == 7 and all("?" not in b for b in books)
    for p in doc.passages:
        assert p.chapter_label.startswith("Book ")
        assert "Liber" not in p.chapter_label and "LIBER" not in p.chapter_label
