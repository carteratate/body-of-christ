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


@pytest.mark.skipif(not _vendored, reason="roman-curia not vendored")
def test_every_vendored_document_builds_clean_passages():
    docs = build_documents()
    assert len(docs) == 61
    for d in docs:
        assert d.collection == "roman-curia"
        assert d.passages, f"{d.title} produced no passages"
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"duplicate anchors in {d.title}"
        for p in d.passages:
            assert not re.search(r"(^|\n)[\[(]\s*\d+\s*[\])]\s", p.content), \
                f"endnote text in {d.title}: {p.content[:80]}"
            assert "DE - EN" not in p.content


@pytest.mark.skipif(not _vendored, reason="roman-curia not vendored")
def test_paragraph_numbers_are_real():
    """A numbered document's §n labels follow its own numbering, in order."""
    by_title = {d.title: d for d in build_documents()}
    nums = [int(p.unit_label[1:]) for p in by_title["Dignitas Infinita"].passages if p.unit_label]
    assert nums == sorted(nums) and nums[0] == 1 and nums[-1] == 66
    # Persona Humana numbers nothing; no passage may claim a paragraph number.
    assert all(p.unit_label is None for p in by_title["Persona Humana"].passages)
