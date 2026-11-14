import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ingest.medieval import build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "medieval")
pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(_SRC, "manifest.json")),
    reason="medieval sources not vendored; run scripts/vendor_sources.py")


def test_anselm_three_works_single_author():
    docs = build_documents()
    anselm = [d for d in docs if d.author == "Anselm"]
    titles = [d.title for d in anselm]
    label = " | ".join(titles)
    # Exactly the three works — no front-matter pseudo-works (Title Page,
    # Introduction, Appendix, Indexes).
    assert len(anselm) == 3, label
    assert any("Proslogium" in t for t in titles), label
    assert any("Monologium" in t for t in titles), label
    assert any("Cur Deus Homo" in t for t in titles), label
    assert not any(t in ("Introduction", "Appendix", "Title Page", "Indexes")
                   for t in titles), label
    assert all(d.author == "Anselm" for d in anselm)


def test_single_works_present_with_year():
    docs = build_documents()
    boeth = [d for d in docs if d.author == "Boethius"]
    assert len(boeth) == 1
    assert boeth[0].year == 524
    assert boeth[0].collection == "medieval"


def test_content_is_clean_and_anchored():
    for d in build_documents():
        assert d.passages, d.title
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not p.content.lstrip().startswith("[")


def test_document_ids_unique():
    ids = [d.id for d in build_documents()]
    assert len(ids) == len(set(ids))


# 1.9, the medieval adapter fixes.

_docs = None


def _built():
    global _docs
    if _docs is None:
        _docs = {d.title: d for d in build_documents()}
    return _docs


def test_anselm_years():
    docs = _built()
    assert docs["Monologium"].year == 1076
    assert docs["Proslogium"].year == 1077
    assert docs["Proslogium"].date_display == "1077 to 1078"
    assert docs["Cur Deus Homo"].year == 1098


def test_cur_deus_homo_retitled_keeps_frozen_id():
    d = _built()["Cur Deus Homo"]
    assert d.id == "82d38756-6fba-5af7-9905-fd508a620f38"
    assert all(p.reference.startswith("Cur Deus Homo, ") for p in d.passages)


def test_cur_deus_homo_keys_unique():
    d = _built()["Cur Deus Homo"]
    keys = {p.chapter_key for p in d.passages}
    assert not any("--" in k for k in keys)
    labels = [p.chapter_label for p in d.passages]
    assert any(label.startswith("Book First · Chapter") for label in labels)
    assert any(label.startswith("Book Second · Chapter") for label in labels)
    assert len(set(p.reference for p in d.passages)) == len(d.passages)


def test_anselm_prefaces_kept_without_editors_summary():
    docs = _built()
    for title, opening in (("Proslogium", "AFTER I had published"),
                           ("Monologium", "CERTAIN brethren have often"),
                           ("Cur Deus Homo", "THE first part of this book")):
        first = docs[title].passages[0]
        assert first.chapter_label == "Preface", title
        assert first.content.startswith(opening), title
    text = " ".join(p.content for p in docs["Proslogium"].passages)
    assert "In this brief work the author aims" not in text


def test_boethius_labels():
    d = _built()["Consolation of Philosophy"]
    assert not any("Introduction" in p.chapter_label for p in d.passages)
    assert {p.chapter_key for p in d.passages} == {"ii", "iii", "iv", "v", "vi"}
    assert {p.chapter_label for p in d.passages} == {"Book I", "Book II", "Book III",
                                                     "Book IV", "Book V"}
    for p in d.passages:
        assert "Cooper" not in p.content
        assert "Theodoric was born" not in p.content
    assert d.metadata["translator"] == "W. V. Cooper"


def test_imitation_foreword_removed():
    d = _built()["Imitation of Christ"]
    assert not any(p.chapter_label == "Foreword" for p in d.passages)
    assert not any("IN PREPARING this edition" in p.content for p in d.passages)
    # Book IV's opening is Thomas's own and stays.
    assert any(p.chapter_label == "An Invitation to Holy Communion · Introduction"
               for p in d.passages)


def test_imitation_chapters_use_their_titles():
    d = _built()["Imitation of Christ"]
    first = next(p for p in d.passages if p.chapter_key == "ONE.1")
    assert first.chapter_label == ("Thoughts Helpful in the Life of the Soul · Imitating "
                                   "Christ and Despising All Vanities on Earth")
    assert not any(p.chapter_label.split(" · ")[-1].startswith("Chapter ")
                   for p in d.passages)


def test_on_loving_god_chapter_viii_title():
    d = _built()["On Loving God"]
    label = next(p.chapter_label for p in d.passages if p.chapter_key == "x")
    # The label carries its chapter number, as its siblings' do ("Chapter I. Why we…").
    assert label == ("Chapter VIII. Of the first degree of love: wherein man loves Self "
                     "for Self's sake")
    assert d.metadata["translator"] == "William Harman van Allen"
    assert d.metadata["edition"] == "Caldey Abbey, Tenby, 1909"
    assert d.metadata["credit_line"] == ("Translated by William Harman van Allen (1909). "
                                         "Sourced via CCEL.org")


def test_bernard_labels_not_cut():
    d = _built()["On Loving God"]
    label = next(p.chapter_label for p in d.passages if p.chapter_key == "iii")
    assert label == "Chapter I. Why we should love God and the measure of that love"


_CF_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")


@pytest.mark.skipif(not os.path.isdir(_CF_SRC), reason="church-fathers sources not vendored")
def test_no_label_cut_mid_word():
    """A label taken from its div's title holds the title whole, or cut between words."""
    from ingest.church_fathers import _read_root
    from publication import SOURCE_ADAPTERS
    docs = list(_built().values()) + SOURCE_ADAPTERS["church-fathers"]()
    titles: dict[str, dict[str, str]] = {}
    cut = []
    for d in docs:
        src = _SRC if d.collection == "medieval" else _CF_SRC
        for p in d.passages:
            f = p.metadata["source_file"]
            if f not in titles:
                titles[f] = {e.get("id"): " ".join((e.get("title") or "").split())
                             for e in _read_root(os.path.join(src, f)).iter() if e.get("id")}
            title = titles[f].get(p.chapter_key, "")
            part = " ".join(p.chapter_label.split(" · ")[-1].split())
            if part and title.casefold().startswith(part.casefold()) \
                    and len(title) > len(part) and title[len(part)].isalnum():
                cut.append(p.chapter_label)
    assert cut == []


@pytest.mark.skipif(not os.path.isdir(_CF_SRC), reason="church-fathers sources not vendored")
def test_roman_numerals_keep_capitals():
    import re
    from publication import SOURCE_ADAPTERS
    from checks.content import roman_case
    docs = SOURCE_ADAPTERS["church-fathers"]()
    assert roman_case("church-fathers", docs) == {}
    assert roman_case("medieval", list(_built().values())) == {}
    papias = next(d for d in docs if d.id == "efc282b4-fe6a-5162-9e1b-8748c686dde1")
    assert any(re.fullmatch(r"VI\.", p.chapter_label) for p in papias.passages)
