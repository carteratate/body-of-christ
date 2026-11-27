"""The Roman Curia collection (5.3a): the Dicastery for the Doctrine of the Faith's
documents, `ingest/roman_curia.py`. The tokenizer tests come from the parked branch
`feat/roman-curia-collection`; the last tests read the vendored pages and skip without
them."""
import os
import re
from datetime import date

import pytest
from bs4 import BeautifulSoup

import document_facts
import headings
import registry
from ingest import roman_curia as RC
from ingest.roman_curia import build_documents, cut_notes, tokens
from registry.genres import ALL_GENRES, CURIA_GENRES

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "roman-curia")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))
needs_sources = pytest.mark.skipif(not _vendored, reason="roman-curia not vendored")

LONG = "This is a sentence of body text long enough to read as prose. " * 3


def _toks(*paras: str):
    html = "<html><body>" + "".join(f"<p>{p}</p>" for p in paras) + "</body></html>"
    return tokens(BeautifulSoup(html, "lxml"))


def test_language_bar_and_title_block_are_dropped():
    toks = _toks("[ DE - EN - ES - FR - IT ]", "DICASTERY FOR THE DOCTRINE OF THE FAITH",
                 "Declaration “Dignitas Infinita” on Human Dignity", f"1. {LONG}")
    assert [k for k, _, _ in toks if k != "title"] == ["para"]
    assert not any("DE - EN" in t for _, _, t in toks)


def test_genre_heading_note_is_not_mistaken_for_endnotes():
    # "NOTE" names the genre at the top of the page; nothing may be cut after it.
    toks = _toks("CONGREGATION FOR THE DOCTRINE OF THE FAITH", "NOTE", LONG, LONG)
    assert sum(1 for k, _, _ in toks if k == "para") == 2


def test_numbered_paragraph_keeps_unnumbered_continuation():
    toks = _toks(f"1. {LONG}", LONG, f"2. {LONG}")
    paras = [(n, t) for k, n, t in toks if k == "para"]
    assert [n for n, _ in paras] == [1, None, 2]


def test_bracketed_notes_are_cut_even_without_note_one():
    body = [f"{n}. {LONG}" for n in range(1, 6)]
    notes = [f"[{n}] Cf. Catechism of the Catholic Church, no. {n}." for n in range(2, 9)]
    kept = cut_notes(body + notes)
    assert kept == body


def test_plain_numbered_notes_after_unnumbered_body_are_cut():
    body = [LONG] * 6
    notes = ["1. Cf. Rom 8:2.", "2. Rom 6:12.", "3. Cf. I Cor 10:13."]
    assert cut_notes(body + notes) == body


def test_numbered_body_without_notes_is_kept():
    body = ["TITLE"] + [f"{n}. {LONG}" for n in range(1, 8)]
    assert cut_notes(body) == body


def test_mid_page_note_run_is_removed():
    lines = [LONG, "(1) Cf. Code of Canon Law, Canon 833.", "(2) Cf. Canon 747.",
             "(3) Cf. Lumen Gentium, 25.", LONG]
    assert cut_notes(lines) == [LONG, LONG]


def test_signature_dropped_and_dateline_kept_with_text():
    toks = _toks(LONG, "Rome, from the Offices of the Congregation, 22 February 2021.",
                 "Luis F. Card. Ladaria, S.I. Prefect")
    paras = [t for k, _, t in toks if k == "para"]
    assert len(paras) == 1 and paras[0].endswith("22 February 2021.")


def test_table_of_contents_is_dropped():
    toks = _toks("NOTE", "Table of Contents", "I. Introduction", "II. Conclusion",
                 "I. Introduction", f"1. {LONG}", "II. Conclusion", f"2. {LONG}")
    sections = [t for k, _, t in toks if k == "section"]
    assert sections == ["I. Introduction", "II. Conclusion"]


def test_numbered_section_title_is_a_heading_not_a_paragraph():
    toks = _toks(f"1. {LONG}", "1. A Growing Awareness of the Centrality of Human Dignity",
                 f"2. {LONG}")
    assert [(k, n) for k, n, _ in toks] == [("para", 1), ("section", None), ("para", 2)]


def test_bare_numbered_notes_are_cut():
    body = [f"{n}. {LONG}" for n in range(1, 6)]
    notes = ["1 Cf. John Paul II, Fides et ratio, 13.", "2 Ibid., 22.", "3 Cf. DS 3074."]
    assert cut_notes(body + notes) == body


def test_question_keeps_its_answer_and_short_reply_joins():
    toks = _toks(LONG, "FIRST QUESTION", "Did the Council change the doctrine on the Church?",
                 "RESPONSE", LONG, "Is it licit to perform the procedure?", "R. Negative.")
    kinds = [(k, t[:10]) for k, _, t in toks]
    assert ("section", "FIRST QUES") in kinds
    paras = [t for k, _, t in toks if k == "para"]
    assert paras[-2].startswith("Response: ")
    assert paras[-1].endswith("R. Negative.")


def test_inline_markers_and_sup_markers_are_removed():
    html = ("<html><body><p>It was stated by the Council.<sup>3</sup></p>"
            f"<p>Among the signs of our age (12) the Church notes this. {LONG}</p></body></html>")
    toks = tokens(BeautifulSoup(html, "lxml"))
    text = " ".join(t for _, _, t in toks)
    assert "(12)" not in text and "Council.3" not in text and "Council. 3" not in text
    # With its marker gone the first line ends a sentence, so it is body text, not title.
    assert toks[0][0] == "para"


def test_latin_paragraph_is_dropped():
    latin = ("Videtur etiam Ecclesiam catholicam esse solam veram Ecclesiam Christi, "
             "quae in terris subsistit et non est nisi una")
    toks = _toks(LONG, latin, LONG)
    assert all("Videtur" not in t for _, _, t in toks)


def test_dateline_and_papal_signature_are_not_headings():
    toks = _toks(LONG, "Vatican City, 10 July 2023", "Leo PP. XIV", LONG)
    assert not any(k == "section" for k, _, _ in toks)




# --------------------------------------------------------------------------- headings

def test_a_documents_tiers_become_levels_and_never_skip():
    runs = [["CHAPTER II", "THE TRAGEDY OF SIN", "I. Preliminary approaches", "A response"],
            ["CHAPTER III", "LIBERATION", "Gospel, freedom and liberation"],
            ["Introduction"]]
    assert RC.heading_levels(runs) == [
        [(1, True), (1, False), (2, False), (3, False)],
        # A plain heading straight under a chapter is level 2, not 3.
        [(1, True), (1, False), (2, False)],
        # An Introduction opens a chapter wherever it falls.
        [(1, False)],
    ]


def test_a_bare_label_pairs_only_with_a_heading_printed_straight_after_it():
    assert RC.heading_levels([["I."], ["The Dignity of the Person"]]) == [
        [(1, False)], [(2, False)]]
    assert RC.heading_levels([["I.", "The Dignity of the Person"]]) == [
        [(1, True), (1, False)]]


def test_a_numeral_printed_without_its_point_is_a_numbered_section():
    assert RC._tier("VI A NEW INTERPRETATION OF CHRISTIANITY") == RC._tier("IX. THE CORE") == 1
    assert RC._tier("I believe in one God") == 2


def test_a_line_of_asterisks_is_dropped():
    assert [k for k, _, _ in _toks(LONG, "* * *", LONG)] == ["para", "para"]


def test_the_top_tier_a_document_uses_is_level_1():
    assert RC.heading_levels([["Explanation"], ["Doubts"]]) == [[(1, False)], [(1, False)]]
    assert RC.heading_levels([["I. Marriage"], ["The family"]]) == [[(1, False)], [(2, False)]]


@pytest.mark.parametrize("raw, label", [
    ("I. THE NATURE OF MARRIAGE", "I. The Nature of Marriage"),
    ("CHAPTER II", "Chapter II"),
    ("CHAPTER I THE STATE OF FREEDOM", "Chapter I The State of Freedom"),
    ("VI A NEW INTERPRETATION OF CHRISTIANITY", "VI A New Interpretation of Christianity"),
])
def test_chapter_labels_keep_numerals_in_capitals(raw, label):
    assert RC._section_label(raw) == label


@pytest.mark.parametrize("text", [
    "Intracytoplasmic sperm injection (ICSI)", 'The "Poor of Yahweh"'])
def test_a_heading_may_end_in_a_bracket_or_a_quotation_mark(text):
    toks = _toks(LONG, text, LONG)
    assert [k for k, _, _ in toks] == ["para", "section", "para"]


# --------------------------------------------------------------------------- facts

@pytest.mark.parametrize("url, day", [
    ("https://x/rc_con_cfaith_doc_19660724_epistula_en.html", date(1966, 7, 24)),
    ("https://x/rc_con_cfaith_doc_28051992_communionis-notio_en.html", date(1992, 5, 28)),
    ("https://x/rc_con_cfaith_risposta-dubia-2023_en.html", None),
])
def test_the_date_is_read_from_the_address(url, day):
    assert RC.document_date({"slug": "x", "url": url}) == day


def test_every_page_kind_maps_to_a_registered_genre():
    assert set(RC.GENRES.values()) <= set(CURIA_GENRES) | {"letter", "other"}
    assert set(RC.GENRES.values()) <= set(ALL_GENRES)


def test_the_issuer_is_the_office_under_the_name_it_printed():
    doc = RC.build_document.__wrapped__ if hasattr(RC.build_document, "__wrapped__") else None
    assert doc is None  # build_document is a plain function
    from model import Document
    built = Document(id="d", collection="roman-curia", title="T",
                     metadata={"genre": "instruction",
                               "issuer_label": "Sacred Congregation for the Doctrine of the Faith"})
    facts = document_facts.derive(built, {"credit_line": document_facts.VATICAN_CREDIT},
                                  {"source_key": "roman-curia/t.html", "work_id": "roman-curia/t"})
    assert (facts["genre"], facts["issuer"], facts["issuer_label"]) == (
        "instruction", "ddf", "Sacred Congregation for the Doctrine of the Faith")
    assert facts["translation"] == "Vatican English"
    assert facts["source_credit"] == document_facts.VATICAN_CREDIT


@pytest.mark.skipif(not _vendored, reason="roman-curia not vendored")
def test_every_vendored_document_builds_clean_passages():
    docs = build_documents()
    assert len(docs) == 60
    for d in docs:
        assert d.collection == "roman-curia"
        assert d.passages, f"{d.title} produced no passages"
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"duplicate anchors in {d.title}"
        units = [p.unit_label for p in d.passages if p.unit_label and "/p" not in p.anchor]
        assert len(units) == len(set(units)), f"repeated paragraph labels in {d.title}"
        for p in d.passages:
            assert len(p.content) >= 25, f"fragment in {d.title}: {p.content!r}"
            assert "DE - EN" not in p.content
            assert not re.search(r"[a-z.,;:”\"»]\s?\(\d{1,3}\)", p.content), \
                f"inline note marker in {d.title}"
            for para in p.content.split("\n\n"):
                assert not re.match(r"^(?:[\[(]\s*\d{1,3}\s*[\])]|\d{1,3}\s+(?:Cf\.|Ibid))", para), \
                    f"endnote text in {d.title}: {para[:80]}"


@pytest.mark.skipif(not _vendored, reason="roman-curia not vendored")
def test_question_and_answer_document_keeps_pairs_together():
    by_title = {d.title: d for d in build_documents()}
    doc = by_title["Responses to Some Questions Regarding Certain Aspects of the Doctrine on the Church"]
    questions = [p for p in doc.passages
                 if re.search(r"^(?:\w+ )?Question\b", p.content, re.M | re.I)]
    assert len(questions) == 5
    for p in questions:
        assert "?" in p.content and "Response:" in p.content, p.anchor
    assert not any("Respondetur" in p.content or "Act Syn" in p.content for p in doc.passages)


@pytest.mark.skipif(not _vendored, reason="roman-curia not vendored")
def test_combined_page_keeps_only_the_commentary():
    by_title = {d.title: d for d in build_documents()}
    doc = by_title["Doctrinal Commentary on the Concluding Formula of the Professio Fidei"]
    text = "\n".join(p.content for p in doc.passages)
    assert doc.passages[0].content.startswith("From her very beginning")
    assert "We order that everything decreed by us" not in text  # the motu proprio


@pytest.mark.skipif(not _vendored, reason="roman-curia not vendored")
def test_paragraph_numbers_are_real():
    """A numbered document's labels follow its own numbering."""
    by_title = {d.title: d for d in build_documents()}
    nums = [int(p.unit_label[1:]) for p in by_title["Dignitas Infinita"].passages if p.unit_label]
    assert nums == sorted(nums) and nums[0] == 1 and nums[-1] == 66
    # Persona Humana numbers nothing; no passage may claim a paragraph number.
    assert all(p.unit_label is None for p in by_title["Persona Humana"].passages)
    # Libertatis Nuntius restarts its numbering in each part, so labels carry the part.
    labels = [p.unit_label for p in by_title["Libertatis Nuntius"].passages if p.unit_label]
    assert "VIII, 3" in labels and "§3" not in labels


@needs_sources
def test_the_sixty_documents_carry_their_facts_and_registered_ids():
    docs = build_documents()
    reg = registry.current()
    assert len(docs) == 60 == len({d.id for d in docs})
    for d in docs:
        key = d.metadata["source_key"]
        assert reg.document_by_key[("roman-curia", key)] == d.id, d.title
        assert d.metadata["genre"] in ALL_GENRES and d.date_display, d.title
        assert d.metadata["issuer_label"].endswith("for the Doctrine of the Faith")
    # The name the page printed: the Sacred Congregation, the Congregation, the Dicastery.
    by_title = {d.title: d for d in docs}
    assert by_title["Cum Oecumenicum Concilium"].metadata["issuer_label"].startswith("Sacred")
    assert by_title["Dignitas Personae"].metadata["issuer_label"].startswith("Congregation")
    assert by_title["Dignitas Infinita"].metadata["issuer_label"].startswith("Dicastery")
    assert by_title["Dignitas Personae"].date_display == "8 September 2008"
    assert "approved" in by_title["Dignitas Personae"].metadata["papal_approval"]


@needs_sources
def test_headings_are_marked_whole_and_open_their_passages():
    for d in build_documents():
        for p in d.passages:
            marks = (p.metadata or {}).get(headings.KEY) or []
            assert headings.problems(p.content, marks) == [], (d.title, p.anchor)
            # A heading opens its passage: nothing comes before the first mark.
            if marks:
                assert min(m["at"] for m in marks) == 0, (d.title, p.anchor)
            if any(m.get("chapter_title") for m in marks):
                assert headings.repeats_label(
                    p.content[marks[0]["at"]:marks[0]["end"]], p.chapter_label) \
                    or marks[0].get("pairs_next"), (d.title, p.anchor)


@needs_sources
def test_every_reference_is_unique_within_its_document():
    for d in build_documents():
        refs = [p.reference for p in d.passages]
        assert len(refs) == len(set(refs)), d.title
