import os, re, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup
from ingest.roman_curia import build_documents, cut_notes, tokens

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "roman-curia")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))

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
    answered = [p for p in doc.passages if "Question" in p.chapter_label]
    assert len({p.chapter_label for p in answered}) == 5
    for label in {p.chapter_label for p in answered}:
        text = "\n".join(p.content for p in answered if p.chapter_label == label)
        assert "?" in text and "Response:" in text
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
