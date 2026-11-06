"""The shared papal parser (corpus-cleanup 1.3a), on synthetic pages so CI runs it; the
vendored checks at the end need the sources."""
import os
import re
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup

from ingest import apostolic_exhortations, encyclicals, papal_common, papal_documents
from ingest.papal_common import tokens
from normalize.footnotes import strip_bare_callers, strip_note_callers

LONG = "These words are long enough to read as a real paragraph of the document. " * 4
_SOURCES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources")
_vendored = os.path.exists(os.path.join(_SOURCES, "encyclicals", "manifest.json"))
vendored = pytest.mark.skipif(not _vendored, reason="papal sources not vendored")


def _page(body: str) -> BeautifulSoup:
    return BeautifulSoup(f'<html><body><div class="entry-content">{body}</div></body></html>',
                         "lxml")


def _paras(toks):
    return [t for t in toks if t.kind == "para"]


def _build(body: str, tmp_path, slug="a-letter", title="A Letter"):
    (tmp_path / f"{slug}.html").write_text(f'<div class="entry-content">{body}</div>',
                                           encoding="utf-8")
    entry = {"slug": slug, "title": title, "author": "Pius", "year": 1900,
             "file": f"{slug}.html", "url": "https://example.org/a"}
    return papal_common.build_document(entry, "encyclicals", str(tmp_path))


def test_three_adapters_share_one_tokenizer():
    for module in (encyclicals, apostolic_exhortations, papal_documents):
        assert module.papal_common is papal_common
        assert not hasattr(module, "_tokens")


def test_li_body_is_kept():
    toks = tokens(_page(f"<p>Greetings and Apostolic Blessing.</p><ol><li>{LONG}</li>"
                        f"<li>Second {LONG}</li></ol><ol start='3'><li>Third {LONG}</li></ol>"))
    assert [(t.number, t.text[:5]) for t in _paras(toks)] == [(1, "These"), (2, "Secon"),
                                                              (3, "Third")]
    assert _paras(toks)[0].segments[0].locator.startswith("l")


def test_list_inside_a_section_stays_in_it():
    toks = tokens(_page(f"<p>1. {LONG}</p><ul><li>one point</li><li>another point</li></ul>"
                        f"<p>2. {LONG}</p>"))
    paras = _paras(toks)
    assert [t.number for t in paras] == [1, 2]
    assert "another point" in paras[0].text


def test_numbered_list_in_a_section_is_not_a_second_section():
    body = "".join(f"<p>{n}. {LONG}</p>" for n in range(1, 6))
    body += "<p>1. First point of a list</p><p>2. Second point of a list</p>"
    body += "".join(f"<p>{n}. {LONG}</p>" for n in range(6, 9))
    paras = _paras(tokens(_page(body)))
    assert [t.number for t in paras] == list(range(1, 9))


def test_word_export_footnotes_are_cut():
    html = (f'<p>1. {LONG}<a name="_ftnref1" href="#_ftn1">[1]</a></p><p>2. {LONG}</p>'
            '<p><a name="_ftn1" href="#_ftnref1">[1]</a> Cf. Jn 3:16.</p><p>Ibid., 12.</p>')
    paras = _paras(tokens(_page(html)))
    assert [t.number for t in paras] == [1, 2]
    assert "[1]" not in paras[0].text and "Ibid" not in paras[1].text


def test_hr_then_numbered_notes_are_cut():
    html = f"<p>1. {LONG}</p><p>2. {LONG}</p><hr/><p>1. Cf. Jn 3:16.</p><p>2. Ibid.</p>"
    assert [t.number for t in _paras(tokens(_page(html)))] == [1, 2]


def test_hr_before_any_number_is_a_masthead_rule():
    html = f"<p>To the Bishops.</p><hr/><p>1. {LONG}</p><p>2. {LONG}</p>"
    assert [t.number for t in _paras(tokens(_page(html)))] == [1, 2]


def test_numbered_heading_is_section():
    html = (f"<p>5. {LONG}</p><p>6. {LONG}</p><p>1. Education</p><p>7. {LONG}</p>")
    toks = tokens(_page(html))
    assert [t.number for t in _paras(toks)] == [5, 6, 7]
    assert any(t.kind == "section" and t.text == "Education" for t in toks)


def test_heading_moves_to_the_next_section(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>Dark Clouds</p><p>2. {LONG}</p>", tmp_path)
    assert doc.passages[0].content.rstrip().endswith("document.")
    assert doc.passages[1].content.startswith("Dark Clouds\n\n")
    assert doc.passages[1].chapter_label == "Dark Clouds"


def test_chapters_are_a_documents_divisions(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>CHAPTER ONE</p><p>DARK CLOUDS</p><p>2. {LONG}</p>"
                 f"<p>Shattered Dreams</p><p>3. {LONG}</p><p>CHAPTER TWO</p><p>4. {LONG}</p>",
                 tmp_path)
    labels = [p.chapter_label for p in doc.passages]
    assert labels == ["Introduction", "Chapter One: Dark Clouds", "Chapter One: Dark Clouds",
                      "Chapter Two"]
    assert doc.passages[2].content.startswith("Shattered Dreams\n\n")


def test_heading_never_sits_alone_on_a_card(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>Dark Clouds</p><p>2. {'A sentence of text. ' * 170}</p>",
                 tmp_path)
    assert all(len(p.content) > 100 for p in doc.passages)


def test_dating_and_signature_join_last_passage(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>2. {LONG}</p><p>Given at Rome, 1 May 1900.</p><p>PAUL VI</p>",
                 tmp_path)
    assert len(doc.passages) == 2
    assert doc.passages[-1].content.endswith("Given at Rome, 1 May 1900.\n\nPAUL VI")


def test_prayers_after_the_last_paragraph(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>2. {LONG}</p><p>Given at Rome.</p><p>A Prayer to the Creator</p>"
                 "<p>Lord, hear us.</p><p>An Ecumenical Prayer</p><p>O God, hear us.</p>", tmp_path)
    assert [p.anchor for p in doc.passages[-2:]] == ["a-letter/prayer-1", "a-letter/prayer-2"]
    assert doc.passages[-2].chapter_label == "A Prayer to the Creator"
    assert doc.passages[-2].content == "Lord, hear us."


def test_implicit_first_paragraph_when_numbering_starts_at_2(tmp_path):
    doc = _build(f"<p>To Our Venerable Brethren.</p><p>Venerable Brethren, Health and "
                 f"Apostolic Benediction.</p><p>{LONG}</p><p>2. {LONG}</p><p>3. {LONG}</p>",
                 tmp_path)
    assert doc.passages[0].anchor == "a-letter/preamble"
    assert len(doc.passages[0].content) < 250
    assert [p.unit_label for p in doc.passages[1:]] == ["§1", "§2", "§3"]


def test_prose_before_paragraph_one_after_a_masthead(tmp_path):
    doc = _build(f"<p>APOSTOLIC LETTER OF THE HOLY FATHER</p><p>{LONG}</p><p>1. {LONG}</p>", tmp_path)
    assert doc.passages[0].anchor == "a-letter/preface"
    assert doc.passages[0].reference == "A Letter, Preface"


def test_bucket_chapter_is_the_document_up_to_twenty_paragraphs(tmp_path):
    doc = _build("".join(f"<p>{n}. {LONG}</p>" for n in range(1, 5)), tmp_path)
    assert {p.chapter_label for p in doc.passages} == {"A Letter"}


def test_unnumbered_source_cites_by_chapter_not_by_an_invented_number(tmp_path):
    doc = _build(f"<p>{LONG}</p><p>{LONG}</p><p><b>The Roman Doctrine</b></p><p>{LONG}</p>", tmp_path)
    assert [p.unit_label for p in doc.passages] == [None, None, None]
    assert doc.passages[0].anchor == "a-letter/1"
    assert doc.passages[-1].anchor == "a-letter/4"     # the heading kept its count
    assert doc.passages[-1].reference == "A Letter, The Roman Doctrine"
    assert doc.passages[0].reference == "A Letter, Introduction (part 1 of 2)"


def test_callers_go_and_numbers_stay():
    html = (f'<p>1. A word<sup>12</sup> and “a quote”<a href="#n3">[3]</a> go on. {LONG}</p>'
            f"<p>2. {LONG}</p>")
    assert "12" not in _paras(tokens(_page(html)))[0].text
    assert strip_note_callers("He said so (35) and more [ 3 ] then.9 Next") == \
        "He said so and more then. Next"
    assert strip_note_callers("See (Rom. 12:10) and (cf. 1 Jn 4:8).") == \
        "See (Rom. 12:10) and (cf. 1 Jn 4:8)."
    assert strip_bare_callers("It is so. 3 For this, sess. 24 On Reform.") == \
        "It is so. For this, sess. 24 On Reform."


@pytest.mark.parametrize("citation", [
    "God is love (cf. 1 Jn 4:16).", "New creation. 2 Cor 5:17.", "Hope (cf. 1 Pt 3:15).",
    "As written. 1 Tim 2:5.", "See 1 Thess 5:19.",
])
def test_a_book_keeps_its_number(citation):
    assert strip_bare_callers(citation) == citation


def test_a_glued_number_before_a_book_is_no_caller():
    assert strip_note_callers("love (cf.1 Jn 4:16).") == "love (cf.1 Jn 4:16)."
    assert strip_note_callers("points out.9 Next") == "points out. Next"


def test_a_wrapped_caller_leaves_no_empty_marker():
    assert strip_note_callers("to nothing)[ ]: so says ( ) he") == "to nothing): so says he"
    html = f'<p>1. It is so (<a href="#n1">1</a>). {LONG}</p><p>2. {LONG}</p>'
    assert "()" not in strip_note_callers(_paras(tokens(_page(html)))[0].text)


def test_syllabus_ends_at_its_last_proposition():
    body = "".join(f"<p>{n}. Proposition number {n} of the list.</p>" for n in range(1, 81))
    toks = tokens(_page(body + f"<p>{LONG}</p><p>{LONG}</p>"), "syllabus-of-errors")
    assert len(_paras(toks)) == 80
    assert _paras(toks)[-1].text == "Proposition number 80 of the list."


def test_list_end_gives_the_closing_its_own_unit(tmp_path):
    body = "".join(f"<p>{n}. Proposition number {n} of the list.</p>" for n in range(1, 42))
    doc = _build(f"{body}<p>{LONG}</p><p>Last {LONG}<span>{{ added text</span></p>"
                 "<p>* Webmaster comment: from a source.</p>", tmp_path, slug="exsurge-domine",
                 title="Exsurge Domine")
    assert doc.passages[40].anchor == "exsurge-domine/41"
    assert doc.passages[40].content == "Proposition number 41 of the list."
    assert doc.passages[41].anchor == "exsurge-domine/closing"
    assert "Webmaster" not in doc.passages[-1].content


def test_editors_words_are_not_emitted(tmp_path):
    doc = _build(f"<p>This Exhortation, which the Holy Father addressed to the clergy.</p>"
                 f"<p>{LONG}</p><p>{LONG}</p>", tmp_path)
    assert not any("Holy Father addressed" in p.content for p in doc.passages)
    assert doc.passages[0].anchor == "a-letter/2"


def test_table_of_contents_is_not_text():
    html = (f"<p>Contents</p><p>INTRODUCTION [1-13]</p><p>1. Living in justice [24-25]</p>"
            f"<p>2. The Church as a sentinel [30]</p><p>INTRODUCTION</p><p>1. {LONG}</p><p>2. {LONG}</p>")
    paras = _paras(tokens(_page(html)))
    assert [t.number for t in paras] == [1, 2]
    assert paras[0].text.startswith("These")


def test_loose_text_in_a_container_is_read():
    html = f"<font>1. {LONG}<br/></font><p>2. {LONG}</p>"
    assert [t.number for t in _paras(tokens(_page(html)))] == [1, 2]


def test_source_url_is_recorded(tmp_path):
    doc = _build(f"<p>1. {LONG}</p>", tmp_path)
    assert doc.metadata["source_url"] == "https://example.org/a"
    assert doc.metadata["pope"] == "Pius"


def test_taken_anchors_name_a_never_live_unit(monkeypatch, tmp_path):
    monkeypatch.setitem(papal_common._UNIT_ANCHORS, "a-letter", {"1": "para-1"})
    doc = _build(f"<p>Greetings and Apostolic Blessing.</p><p>{LONG}</p><p>2. {LONG}</p>", tmp_path)
    assert doc.passages[1].anchor == "a-letter/para-1"
    assert doc.passages[1].unit_label == "§1"


@pytest.fixture(scope="module")
def built():
    docs = encyclicals.build_documents() + apostolic_exhortations.build_documents() \
        + papal_documents.build_documents()
    return {d.metadata["source_key"].split("/", 1)[1]: d for d in docs}


def _chars(doc) -> int:
    return sum(len(p.content) for p in doc.passages)


@vendored
def test_list_bodies_are_kept(built):
    assert _chars(built["in-dominico-agro"]) >= 9500
    assert _chars(built["annus-qui-hunc"]) >= 60_000


@vendored
def test_no_passage_is_a_wall_of_citations(built):
    marker = re.compile(r"AAS|Ibid\.|op\. cit\.|Cf\.")
    # The Syllabus cites its source after each short proposition.
    walls = [p.anchor for slug, d in built.items() if slug != "syllabus-of-errors"
             for p in d.passages
             if len(marker.findall(p.content)) * 1000 / len(p.content) >= 4]
    assert walls == []


@vendored
def test_no_short_passages(built):
    assert [p.anchor for d in built.values() for p in d.passages if len(p.content) < 20] == []


@vendored
def test_quanta_cura_paragraphs(built):
    doc = built["quanta-cura-1864"]
    labels = list(dict.fromkeys(p.unit_label for p in doc.passages if p.unit_label))
    assert labels == [f"§{n}" for n in range(1, 13)]
    assert len(doc.passages[0].content) < 250
    assert doc.passages[1].anchor == "quanta-cura-1864/para-1"
    assert not any(p.content.startswith("Gregory XVI, encyclical epistle") for p in doc.passages)


@vendored
def test_condemned_lists_end_at_their_propositions(built):
    syllabus = built["syllabus-of-errors"]
    assert len({p.unit_label for p in syllabus.passages if p.unit_label}) == 80
    assert syllabus.passages[-1].anchor == "syllabus-of-errors/80"
    exsurge = built["exsurge-domine"]
    assert len({p.unit_label for p in exsurge.passages if p.unit_label}) == 41
    last = next(p for p in exsurge.passages if p.anchor == "exsurge-domine/41")
    assert "\n" not in last.content


@vendored
def test_fratelli_tutti_shows_eight_titled_chapters(built):
    labels = list(dict.fromkeys(p.chapter_label for p in built["fratelli-tutti"].passages))
    assert len([x for x in labels if x.startswith("Chapter ")]) == 8
    assert "Chapter One: Dark Clouds Over a Closed World" in labels


def test_text_under_a_heading_with_no_number_is_its_own_unit(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>IV. SOCIALISM AND SECRET SOCIETIES</p><p>Pests of this kind. {LONG}</p>"
                 f"<p>V. ERRORS CONCERNING THE CHURCH</p><p>2. {LONG}</p>", tmp_path)
    prose = doc.passages[1]
    assert prose.anchor == "a-letter/text-1"
    assert prose.chapter_label == "IV. Socialism and Secret Societies"
    assert "Pests of this kind." in prose.content
    assert doc.passages[2].unit_label == "§2"
    assert "Pests" not in doc.passages[2].content


def test_dating_after_the_prayers_joins_the_last_prayer(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>2. {LONG}</p><p>A Prayer to the Creator</p><p>Lord, hear us.</p>"
                 "<p>Amen</p><p>Given at Rome, 1 May 1900.</p><p>Franciscus</p>", tmp_path)
    assert doc.passages[-1].content == \
        "Lord, hear us.\n\nAmen\n\nGiven at Rome, 1 May 1900.\n\nFranciscus"


def test_long_opening_paragraph_may_begin_with_a_vocative(tmp_path):
    doc = _build(f"<p>To Our Sons.</p><p>Beloved sons and venerable brothers, {LONG}</p><p>2. {LONG}</p>",
                 tmp_path)
    assert [p.unit_label for p in doc.passages] == [None, "§1", "§2"]
    assert doc.passages[1].content.startswith("Beloved sons")


def test_preface_keeps_prose_ending_in_a_semicolon(tmp_path):
    doc = _build(f"<p>APOSTOLIC LETTER OF THE HOLY FATHER</p><p>{LONG}</p><p>Oh! {LONG};</p>"
                 f"<p>1. {LONG}</p>", tmp_path)
    assert "Oh!" in doc.passages[0].content


def test_division_before_text_before_the_first_number(tmp_path):
    doc = _build(f"<p>APOSTOLIC LETTER OF THE HOLY FATHER</p><p>{LONG}</p>"
                 f"<p align='center'><b>PART I</b></p><p>Second {LONG}</p><p>1. {LONG}</p>", tmp_path)
    assert [p.chapter_label for p in doc.passages][:2] == ["Introduction", "Part I"]
    assert doc.passages[1].reference == "A Letter, Part I"


def test_a_division_with_no_text_of_its_own_stays_in_the_label(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>PART FOUR</p><p>PASTORAL CARE</p><p>I. Stages of Care</p>"
                 f"<p>2. {LONG}</p><p>II. Structures</p><p>3. {LONG}</p>", tmp_path)
    assert doc.passages[1].chapter_label == "Part Four: Pastoral Care: I. Stages of Care"
    assert doc.passages[2].chapter_label == "II. Structures"


def test_masthead_of_an_unnumbered_source_is_no_chapter(tmp_path):
    doc = _build(f"<p>APOSTOLIC EXHORTATION OF HIS HOLINESS</p><p>May 9, 1975</p><p>{LONG}</p>"
                 f"<p>{LONG}</p>", tmp_path)
    assert doc.passages[0].anchor == "a-letter/2"
    assert doc.passages[0].content.startswith("These")
    assert doc.passages[0].chapter_label == "A Letter"


def test_unnumbered_source_of_any_length_has_no_paragraph_ranges(tmp_path):
    doc = _build("".join(f"<p>{LONG}</p>" for _ in range(25)), tmp_path)
    assert {p.chapter_label for p in doc.passages} == {"A Letter"}
    assert doc.passages[1].reference == "A Letter (part 2 of 25)"


def test_notes_heading_run_on_to_the_last_line_goes(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>Given at Rome, 1 May 1900. REFERENCES:</p>", tmp_path)
    assert doc.passages[-1].content.endswith("1 May 1900.")


@pytest.mark.parametrize("raw,label", [
    ("II. THE ISSUE OF WATER", "II. The Issue of Water"),
    ("VIII. THE PRAYER OF THE CHURCH", "VIII. The Prayer of the Church"),
    ('CHAPTER II - THE FRUITS OF DIALOGUE', "Chapter II - The Fruits of Dialogue"),
    ('"YOU SHALL BE MY WITNESSES"', '"You Shall Be My Witnesses"'),
])
def test_chapter_labels_are_cased(raw, label):
    assert papal_common._chapter_label(raw) == label


@vendored
def test_syllabus_prose_is_outside_the_propositions(built):
    syllabus = built["syllabus-of-errors"]
    by_anchor = {p.anchor: p for p in syllabus.passages}
    assert "Pests of this kind" not in by_anchor["syllabus-of-errors/19"].content
    assert "Pests of this kind" in by_anchor["syllabus-of-errors/text-4"].content


@vendored
def test_every_document_numbering_from_two_has_its_first_paragraph(built):
    assert [slug for slug, d in built.items()
            if any(p.unit_label == "§2" for p in d.passages)
            and not any(p.unit_label == "§1" for p in d.passages)] == []


def test_short_list_after_a_rule_is_notes():
    html = f"<p>1. {LONG}</p><p>2. {LONG}</p><p>Given at Rome.</p><hr/><ol><li>22.32.</li><li>I Cor 4.21.</li></ol>"
    assert "Cor" not in _paras(tokens(_page(html)))[-1].text


def test_dating_after_the_rule_stays_and_notes_go():
    html = (f"<p>1. {LONG}</p><p>2. {LONG}</p><hr/><p>Given at Rome, 1 May 1961.</p>"
            "<p>REFERENCES:</p><ul><li>1. Cf. 1 Tim. 3:15.</li></ul>")
    last = _paras(tokens(_page(html)))[-1].text
    assert last.endswith("Given at Rome, 1 May 1961.")


def test_site_logo_is_not_text():
    html = f"<p>1. {LONG}</p><p>2. {LONG}</p><h2>The Holy See</h2>"
    assert "Holy See" not in _paras(tokens(_page(html)))[-1].text


def test_bare_division_takes_its_title_past_an_epigraph(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>CHAPTER ONE</p><p>WE HAVE BELIEVED IN LOVE (cf. 1 Jn 4:16)</p>"
                 f"<p>“Go, take the scroll.”</p><p>2. {LONG}</p><p>CHAPTER TWO</p><p>3. {LONG}</p>",
                 tmp_path)
    assert doc.passages[1].chapter_label == "Chapter One: We Have Believed in Love (cf. 1 Jn 4:16)"
    assert "scroll" in doc.passages[1].content


def test_short_epigraph_before_a_subsection_is_no_card(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>CHAPTER TWO</p><p>THE GOSPEL OF HOPE</p><p>“Go, take the scroll.”</p>"
                 f"<p>I. The Lord calls</p><p>2. {LONG}</p><p>II. The whole Church</p><p>3. {LONG}</p>",
                 tmp_path)
    assert not any("/text-" in p.anchor for p in doc.passages)
    assert doc.passages[1].chapter_label == "Chapter Two: The Gospel of Hope: I. The Lord calls"


def test_run_on_number_splits_its_block():
    html = f"<p>1. {LONG}</p><p>2. {LONG}[38] 3. And here we are.</p><p>False Accusations 4. We wrote.</p><p>5. {LONG}</p>"
    assert [t.number for t in _paras(tokens(_page(html)))] == [1, 2, 3, 4, 5]


def test_misprinted_number_takes_the_one_the_run_leaves_free(monkeypatch):
    monkeypatch.setitem(papal_common._NUMBER_FIXES, "a-letter", {"90. In the first": 3})
    html = f"<p>1. {LONG}</p><p>2. {LONG}</p><p>90. In the first {LONG}</p><p>4. {LONG}</p>"
    assert [t.number for t in _paras(tokens(_page(html), "a-letter"))] == [1, 2, 3, 4]


def test_division_with_final_punctuation_is_a_chapter(tmp_path):
    doc = _build(f"<p>1. {LONG}</p><p>CHAPTER I - WHAT GOOD MUST I DO? (Mt 19:16)</p><p>2. {LONG}</p>"
                 f"<p>CHAPTER II - QUANTA EST NOBIS VIA?</p><p>3. {LONG}</p>", tmp_path)
    assert doc.passages[1].chapter_label.startswith("Chapter I - What Good Must I Do?")
    assert doc.passages[0].content.rstrip().endswith("document.")


def test_a_word_beginning_part_is_no_division():
    assert not papal_common._MAJOR.match("Participation in the Eucharist")
    assert papal_common._MAJOR.match("Part One")


def test_short_line_closing_on_a_reference_is_a_heading(tmp_path):
    doc = _build(f'<p>1. {LONG}</p><p>"We cannot but speak" (Acts 4:20)</p><p>2. {LONG}</p>', tmp_path)
    assert doc.passages[1].content.startswith('"We cannot but speak"')


def test_a_very_long_opening_takes_its_headings_as_chapters(tmp_path):
    long = "These words are long enough to read as a real paragraph of the document. " * 45
    body = "".join(f"<p>{n}. {long}</p>" for n in range(1, 8))
    body += f"<p>8. {long}</p><p><i>Is hope individualistic?</i></p>" + "".join(
        f"<p>{n}. {long}</p>" for n in range(9, 18))
    body += f"<p><b>I. Prayer as a school of hope</b></p><p>18. {long}</p>" \
        f"<p><b>II. Action and suffering</b></p><p>19. {long}</p>"
    labels = list(dict.fromkeys(p.chapter_label for p in _build(body, tmp_path).passages))
    assert labels == ["Introduction", "Is hope individualistic?", "I. Prayer as a school of hope",
                      "II. Action and suffering"]


@vendored
def test_mulieris_dignitatem_keeps_its_book_numbers(built):
    text = " ".join(p.content for p in built["mulieris-dignitatem"].passages)
    assert "1 Jn 4:16" in text and "2 Cor 5:17" in text
    assert not re.search(r"\(cf\. (?:Cor|Pt|Tm)\b", text)


@vendored
def test_no_empty_markers(built):
    assert [p.anchor for d in built.values() for p in d.passages
            if re.search(r"\(\s*\)|\[\s*\]", p.content)] == []
