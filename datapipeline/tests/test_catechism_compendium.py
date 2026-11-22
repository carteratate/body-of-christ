"""The Compendium of the Catechism adapter (corpus-cleanup 5.5).

The first tests read a small page shaped like vatican.va's; the last ones read the
vendored page and skip without it."""
import os

import pytest

from ingest import catechism_compendium as C

PAGE = """<html><body><div id="corpo">
<p><a href="#x">Part One</a></p>
<p align="center"><font size="4"><b>MOTU PROPRIO</b></font></p>
<p>Twenty years ago, work began.</p>
<p align="center"><font color="#663300" size="5"><b>Part One</b></font></p>
<p align="center"><font color="#663300" size="4"><b><a name="a">The Profession of Faith</a></b></font></p>
<p align="center"><font color="#663300"><b><a name="b">Section One<br/>"I believe"</a></b></font></p>
<p><b>1. What is the plan of God for man?</b></p>
<p>1-25</p>
<p>God freely created man (<i>Genesis</i> 1:27).</p>
<p align="center"><font color="#663300"><b>CHAPTER ONE</b></font></p>
<p align="center"><font color="#663300"><b><a name="c">Man's Capacity for God</a></b></font></p>
<p>30</p>
<blockquote><p><i>"You have made us for yourself."</i> (Saint Augustine)</p></blockquote>
<p><b>2. Why does man have a desire for God?</b></p>
<p>27-30<br/> 44-45</p>
<p>God has written upon his heart the desire to see him.</p>
<blockquote><p><i>"A saying."</i> (Saint Cyprian)</p></blockquote>
<p align="center"><font color="#663300"><b>THE SACRAMENTS OF THE CHURCH</b></font></p>
<p align="center"><font color="#663300" size="4"><b>Who celebrates?</b></font></p>
<p><b>3 . What does it forbid?</b></p>
<p>2475-2487, 2507</p>
<p>It forbids:</p>
<ul><li>false witness;</li><li>rash judgment.</li></ul>
<p align="center"><font color="#663300" size="4"><b>The Creed</b></font></p>
<p>I believe in God the Father almighty.</p>
<p align="center"><b>APPENDIX</b></p>
<p>In the name of the Father.</p>
</div></body></html>"""


@pytest.fixture
def page(tmp_path):
    path = tmp_path / "compendium.html"
    path.write_bytes(PAGE.encode("latin-1"))
    return str(path)


def test_each_question_with_its_answer_and_sayings_is_one_passage(page):
    built = C.build(page, questions=3)
    passages = built.document.passages
    assert [p.anchor for p in passages] == ["q/1", "q/2", "q/3"]
    assert passages[0].content == ("1. What is the plan of God for man?\n\n"
                                   "God freely created man (Genesis 1:27).")
    assert passages[1].content.endswith('desire to see him.\n\n"A saying." (Saint Cyprian)')
    assert passages[2].content == ("3. What does it forbid?\n\nIt forbids:\n\n"
                                   "false witness;\n\nrash judgment.")
    assert [p.reference for p in passages][1] == "Compendium of the Catechism, Q. 2"
    assert [p.unit_label for p in passages] == ["Q. 1", "Q. 2", "Q. 3"]


def test_ccc_references_are_kept_out_of_the_text_as_ranges(page):
    passages = C.build(page, questions=3).document.passages
    assert [p.metadata["ccc_references"] for p in passages] == [
        [[1, 25]], [[27, 30], [44, 45]], [[2475, 2487], [2507, 2507]]]
    assert not any("§" in p.content + p.reference + p.unit_label for p in passages)


def test_chapters_follow_the_headings_above_each_question(page):
    passages = C.build(page, questions=3).document.passages
    assert [(p.chapter_key, p.chapter_label) for p in passages] == [
        ("compendium/part-1/section-1", 'Part One, Section One, "I believe"'),
        ("compendium/part-1/section-1/chapter-1",
         "Part One, Section One, Chapter One, Man's Capacity for God"),
        ("compendium/part-1/section-1/chapter-1/the-sacraments-of-the-church/who-celebrates",
         "Part One, Section One, Chapter One, The Sacraments of the Church, Who celebrates?"),
    ]


def test_texts_between_sections_and_the_front_and_back_matter_are_left_out(page):
    built = C.build(page, questions=3)
    assert built.skipped == ["30", '"You have made us for yourself." (Saint Augustine)',
                             "The Creed", "I believe in God the Father almighty."]
    text = " ".join(p.content for p in built.document.passages)
    assert "Twenty years" not in text and "In the name of the Father" not in text


def test_the_question_count_is_checked(page):
    with pytest.raises(ValueError, match="3 questions, expected 598"):
        C.build(page)


def test_a_misprinted_reference_line_is_corrected_only_where_it_is_misprinted(page, monkeypatch):
    monkeypatch.setattr(C, "REFERENCE_FIXES", {2: ("27-30 44-45", "27-30")})
    assert C.build(page, questions=3).document.passages[1].metadata["ccc_references"] \
        == [[27, 30]]
    monkeypatch.setattr(C, "REFERENCE_FIXES", {2: ("2112-213", "212-213")})
    with pytest.raises(ValueError, match="not the misprint"):
        C.build(page, questions=3)


def test_a_reference_outside_the_catechism_stops_the_build():
    with pytest.raises(ValueError, match="out of range"):
        C.ccc_references("2112-213")


# --------------------------------------------------------------------------- the page

needs_page = pytest.mark.skipif(not os.path.exists(C._DEFAULT_SRC),
                                reason="needs the vendored sources/catechism/compendium-ccc.html")


@pytest.fixture(scope="module")
def vendored():
    return C.build()


@needs_page
def test_the_page_gives_598_questions_each_one_passage(vendored):
    passages = vendored.document.passages
    assert [p.anchor for p in passages] == [f"q/{n}" for n in range(1, 599)]
    assert all(p.content.startswith(f"{n}. ") for n, p in enumerate(passages, 1))
    assert all(p.metadata["ccc_references"] for p in passages)
    assert passages[38].metadata["ccc_references"] == [[212, 213]]   # misprinted 2112-213


@needs_page
def test_the_page_leaves_out_only_the_texts_between_sections(vendored):
    skipped = vendored.skipped
    assert len(skipped) == 57
    assert skipped[:3] == ["30", skipped[1], "The Creed"] and "Augustine" in skipped[1]
    assert [s for s in skipped if s.endswith(":") or s in (
        "Exodus 20:2-17", "Deuteronomy 5:6-21", "A Traditional Catechetical Formula",
        "Our Father", "Septem Ecclesiae Sacramenta")] == [
        "The seven sacraments are:", "Septem Ecclesiae Sacramenta", "Exodus 20:2-17",
        "Deuteronomy 5:6-21", "A Traditional Catechetical Formula", "Our Father"]


@needs_page
def test_the_page_document_is_the_rights_row_s_work(vendored):
    d = vendored.document
    assert (d.collection, d.title, d.author, d.year) == ("catechism", C.TITLE, None, 2005)
    assert d.metadata["url"].startswith("https://www.vatican.va/")
    assert len({p.chapter_key for p in d.passages}) == 92


# --------------------------------------------------------------------------- the checks

def test_the_source_check_reads_the_page_without_the_adapter(page):
    from checks.source_text import compendium_units

    units = compendium_units(page)
    assert (units[0].text, units[0].region) == ("Part One", "toc")    # the contents
    regions = {u.text: u.region for u in units[1:]}
    assert regions["Twenty years ago, work began."] == "body"     # the motu proprio
    assert regions["27-30 44-45"] == "apparatus"
    assert regions["CHAPTER ONE"] == "heading"
    assert regions["God freely created man (Genesis 1:27)."] == "body"
    assert regions["I believe in God the Father almighty."] == "body"


def test_coverage_places_each_catechism_document_on_its_own_file(page):
    from checks.coverage import documents_by_file
    from checks.source_text import CCC_FILE
    from model import Document

    ccc = Document(id="ccc", collection="catechism", title="Catechism of the Catholic Church",
                   metadata={"source_key": "catechism"})
    compendium = C.build(page, questions=3).document
    placed = documents_by_file("catechism", [ccc, compendium], [CCC_FILE, C.SOURCE_FILE])
    assert placed == {CCC_FILE: [ccc], C.SOURCE_FILE: [compendium]}


def test_the_ccc_paragraph_checks_read_only_the_ccc(page):
    from checks.report import ccc_documents
    from model import Document

    ccc = Document(id="ccc", collection="catechism", title="Catechism of the Catholic Church",
                   metadata={"source_key": "catechism"})
    assert ccc_documents([ccc, C.build(page, questions=3).document]) == [ccc]


@needs_page
def test_the_ccc_1471_sentinel_reads_only_the_ccc(page):
    from checks.report import SENTINELS, sentinel_value
    from checks.source_text import CCC_FILE, file_units
    from model import Document, Passage

    units = file_units("catechism", CCC_FILE)
    [paragraph] = [u.text for u in units if u.region == "body" and u.unit_id == "1471"]
    compendium = C.build(page, questions=3).document
    compendium.passages[0].content = paragraph
    ccc = Document(id="ccc", collection="catechism", title="Catechism of the Catholic Church",
                   metadata={"source_key": "catechism"},
                   passages=[Passage("Other words.", "CCC §1", "ccc/1", "k", "l", 0)])
    sentinel = next(s for s in SENTINELS if s.name == "ccc_1471_definition")
    assert sentinel_value(sentinel, [ccc, compendium], units) == 0
    assert sentinel_value(sentinel, [Document(**{**vars(ccc), "passages": compendium.passages})],
                          units) == 1
