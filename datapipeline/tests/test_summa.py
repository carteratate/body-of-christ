"""The Summa adapter (corpus-cleanup 1.7): the paragraph walk, citations, prologues,
recovered units and the checks that guard them.

Fixture tests build small ThML articles shaped like the reviewed cases, so they run
without the gitignored `sources/`; the source checks at the end need summa.xml.
"""
import itertools
import json
import os
import re
from collections import Counter

import pytest

from checks import content, structure
from config import settings
from ingest import summa
from ingest.common import DISPLAY_PASSAGE_MAX_OVERSHOOT
from ingest.summa import build_document

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "summa", "summa.xml")
_needs_sources = pytest.mark.skipif(
    not os.path.exists(_SRC),
    reason="summa sources not vendored; run scripts/vendor_sources.py")

NO_CORRECTIONS = {"paragraphs": {}, "articles": {}}
NO_RECOVERED = {"editions": {}, "units": [], "in_place": []}


def _xml(articles: str, *, part="FP", part_title="First Part", question="Q1",
         q_title="Question. 1 - OF THINGS (TWO ARTICLES)", prologue="") -> str:
    return (f'<ThML><ThML.body><div1 title="{part_title}" id="{part}">'
            f'<div2 title="Treatise" id="{part}.i">'
            f'<div3 title="{q_title}" id="{part}_{question}">{prologue}{articles}'
            f'</div3></div2></div1></ThML.body></ThML>')


def _article(art: str, paras: list[str], title="Article. 1 - Whether it is so?") -> str:
    body = "".join(f'<p id="{art}-p{k}">{text}</p>' for k, text in enumerate(paras, 1))
    return f'<div4 title="{title}" id="{art}">{body}</div4>'


def _build(tmp_path, xml, corrections=None, recovered=None):
    path = tmp_path / "summa.xml"
    path.write_text(xml, encoding="utf-8")
    return build_document(str(path), corrections or NO_CORRECTIONS,
                          recovered or NO_RECOVERED)


def _labels(doc):
    return [k for k, _ in itertools.groupby(p.unit_label for p in doc.passages)]


B = "<b>{}</b> {}".format
OBJ = [B("Objection 1:", "It would seem that it is not so."),
       B("Objection 2:", "Further, another argument."),
       B("Objection 3:", "Further, a third argument.")]
SED = B("On the contrary,", "Augustine says that it is so.")
RESP = B("I answer that,", "It is so, as the argument shows.")
REPLIES = [B(f"Reply to Objection {n}:", f"The argument {n} does not follow.") for n in (1, 2, 3)]


# --------------------------------------------------------------------------- the walk

def test_objection_with_on_the_contrary_words_stays_an_objection(tmp_path):
    """FP_Q29_A2's shape: the translators print a sed contra as "Objection 4: On the
    contrary, ...". A phrase inside a paragraph never starts a part."""
    paras = OBJ + [B("Objection 4:", "On the contrary, Boethius says that genera subsist."),
                   B("Objection 5:", "Further, Boethius says that matter is hypostasis."),
                   SED, RESP] + REPLIES
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert _labels(doc)[:7] == ["Objection 1", "Objection 2", "Objection 3", "Objection 4",
                                "Objection 5", "On the contrary", "I answer that"]
    assert doc.passages[3].content.startswith("On the contrary, Boethius")


def test_printed_sed_contra_objection_cites_its_latin_role(tmp_path):
    """R7 question 1 (Carter, 12 Nov 2026): the printed label and number stay, the
    citation gives the Latin role, and the voice is rejected unless Aquinas grants it."""
    paras = OBJ + [B("Objection 4:", "On the contrary, Tully says that justice is first."),
                   B("Objection 5:", "Further, liberality is more useful."), RESP] + REPLIES
    facts = {"latin_role": "sed-contra", "latin_number": 1,
             "latin": ["II-II q. 123 a. 12 s. c. 1 [CT 44134]"]}
    corrections = {"paragraphs": {"SS_Q1_A1-p4": facts,
                                  "SS_Q1_A1-p5": {**facts, "latin_number": 2}},
                   "articles": {}}
    doc = _build(tmp_path, _xml(_article("SS_Q1_A1", paras), part="SS",
                                part_title="Second Part of the Second Part"), corrections)
    four, five = doc.passages[3], doc.passages[4]
    assert (four.unit_label, five.unit_label) == ("Objection 4", "Objection 5")
    assert ", sed contra 1: " in four.reference and ", sed contra 2: " in five.reference
    assert four.voice == five.voice == "rejected"
    assert "SS_Q123_A12-p5" in summa.GRANTED and "SS_Q136_A5-p5" in summa.GRANTED


def test_unmarked_respondeo_after_sed_contra(tmp_path):
    """FP_Q68_A2: the determination opens "I answer with Augustine", with no marker."""
    paras = OBJ + [SED, "I answer with Augustine that these words have authority."] + REPLIES
    corrections = {"paragraphs": {}, "articles": {"FP_Q1_A1": {
        "unmarked_determination": "FP_Q1_A1-p5"}}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections)
    determinations = [p for p in doc.passages if p.unit_label == "I answer that"]
    assert len(determinations) == 1
    assert determinations[0].content.startswith("I answer with Augustine")


def test_unbold_sed_contra_stays_sed_contra(tmp_path):
    """SS_Q23_A2: "On the contrary," opens a paragraph without bold."""
    paras = OBJ + ["On the contrary, Augustine says that charity is a movement.", RESP]
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert _labels(doc) == ["Objection 1", "Objection 2", "Objection 3", "On the contrary",
                            "I answer that"]
    assert not content.summa_unbold_openings([doc])


def test_unbold_determination(tmp_path):
    """TP_Q44_A1: "I answer that," opens a paragraph without bold."""
    paras = OBJ + [SED, "I answer that, The miracles were arguments for the faith."]
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert _labels(doc)[-1] == "I answer that"


def test_contrary_however_is_not_part_of_an_objection(tmp_path):
    """I-II q.46 a.7: "The contrary, however, ..." is the sed contra, not objection 3's
    last paragraph."""
    paras = OBJ + ["The contrary, however, may be gathered from the Philosopher.", RESP]
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    sed = [p for p in doc.passages if p.unit_label == "On the contrary"]
    assert len(sed) == 1 and sed[0].content.startswith("The contrary, however")
    assert "contrary" not in doc.passages[2].content


def test_comma_less_opening_starts_a_part(tmp_path):
    """Four Supplement paragraphs open "I answer that There are ..." with no comma."""
    paras = OBJ + [SED, "I answer that There are two reasons."]
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert _labels(doc)[-1] == "I answer that"


def test_phrase_inside_a_paragraph_starts_nothing(tmp_path):
    paras = OBJ + [SED, B("I answer that,", "As stated above (Arg. On the contrary), it is so. "
                          "On the contrary, some say otherwise.")]
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert _labels(doc)[-2:] == ["On the contrary", "I answer that"]


def test_corrected_label_reply_not_objection(tmp_path):
    """SS_Q172_A1: a reply whose bold label says "Objection 2"."""
    paras = OBJ + [SED, RESP, REPLIES[0], B("Objection 2:", "The prophets were inspired."),
                   REPLIES[2]]
    corrections = {"paragraphs": {"FP_Q1_A1-p7": {
        "role": "reply", "targets": ["obj 2"], "latin": ["II-II q. 172 a. 1 ad 2 [CT 1]"]}},
        "articles": {}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections)
    reply = next(p for p in doc.passages if p.anchor == "summa/FP_Q1_A1/p7")
    assert reply.unit_label == "Reply to Objection 2" and reply.voice is None
    assert reply.content.startswith("The prophets")
    assert not content.summa_objection_after_replies([doc])


def test_editorial_section_excluded_before_roles(tmp_path):
    """TP_Q26_A2: the edition's essay after reply 3 is excluded before roles are given,
    so it neither joins the reply nor opens a part of its own."""
    paras = OBJ + [SED, RESP] + REPLIES + ["ST. THOMAS AND THE IMMACULATE CONCEPTION",
                                            "The doctrine was defined in 1854."]
    flag = {"role": "editorial", "flag": "editorial"}
    corrections = {"paragraphs": {"FP_Q1_A1-p9": flag, "FP_Q1_A1-p10": flag}, "articles": {}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections)
    assert doc.passages[-1].unit_label == "Reply to Objection 3"
    assert "1854" not in doc.passages[-1].content
    assert [e["paragraph"] for e in doc.metadata["excluded_paragraphs"]] == [
        "FP_Q1_A1-p9", "FP_Q1_A1-p10"]
    assert not content.summa_editor_supplied([doc], corrections)


def test_supplied_reply_acted_on_before_note_strip(tmp_path):
    """I-II q.102 a.6 ad 10: the "supplied by Nicolai" warning is a bracketed note, which
    the apparatus strip would remove. The flag acts on the paragraph first, so the reply
    leaves the build whole instead of losing only its warning."""
    supplied = B("Reply to Objection 3:", "[*The Reply is lacking in the codices, and was "
                 "supplied by Nicolai.] Silver and gold were reasonable.")
    paras = OBJ + [SED, RESP] + REPLIES[:2] + [supplied]
    corrections = {"paragraphs": {"FP_Q1_A1-p8": {"flag": "editor-supplied"}}, "articles": {}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections)
    assert not any("Silver" in p.content for p in doc.passages)
    assert doc.metadata["excluded_paragraphs"] == [
        {"paragraph": "FP_Q1_A1-p8", "why": "editor-supplied"}]
    unflagged = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert unflagged.passages[-1].content == "Silver and gold were reasonable."
    flagged = {"paragraphs": {"FP_Q1_A1-p8": {"flag": "editor-supplied"}}}
    assert content.summa_editor_supplied([unflagged], flagged)


def test_two_articles_in_one_div_split(tmp_path):
    """SS_Q64_A7 holds a.8 from its title paragraph on (C-07): a.8 gets its own chapter
    and citation, and its passages keep their anchors in a.7's div (D1)."""
    paras = OBJ[:1] + [SED, RESP, REPLIES[0], "Whether one is guilty by chance?",
                       OBJ[0], SED, RESP, REPLIES[0]]
    moved = {"move_to": "SS_Q1_A2"}
    corrections = {"paragraphs": {f"SS_Q1_A1-p{k}": dict(moved) for k in range(5, 10)},
                   "articles": {"SS_Q1_A2": {"from_div": "SS_Q1_A1",
                                             "first_paragraph": "SS_Q1_A1-p5"}}}
    corrections["paragraphs"]["SS_Q1_A1-p5"]["role"] = "article-title"
    doc = _build(tmp_path, _xml(_article("SS_Q1_A1", paras), part="SS",
                                part_title="Second Part of the Second Part"), corrections)
    second = [p for p in doc.passages if p.metadata["article"] == "SS_Q1_A2"]
    assert [p.anchor for p in second] == [f"summa/SS_Q1_A1/p{k}" for k in (6, 7, 8, 9)]
    assert second[0].reference == ("Summa Theologiae II-II, q. 1, a. 2, obj. 1: "
                                   "Whether one is guilty by chance?")
    assert len({p.chapter_key for p in second}) == 1
    assert second[0].chapter_key != doc.passages[0].chapter_key


def test_joint_reply_targets(tmp_path):
    """"Reply OBJ 2 and 3:" is one reply to two objections."""
    paras = OBJ + [SED, RESP, REPLIES[0], "Reply OBJ 2 and 3: These reasons refer to grace."]
    corrections = {"paragraphs": {"FP_Q1_A1-p7": {
        "role": "reply", "targets": ["obj 2", "obj 3"], "latin": ["I q. 93 a. 4 ad 2 [CT 1]"]}},
        "articles": {}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections)
    joint = doc.passages[-1]
    assert joint.unit_label == "Reply to Objections 2 and 3"
    assert joint.metadata["reply_targets"] == ["obj 2", "obj 3"]
    assert ", ad 2 and 3: " in joint.reference
    assert joint.content == "These reasons refer to grace."


def test_reply_to_sed_contra_target(tmp_path):
    """A reply to a sed contra argument: the Leonine numbers it after the objections."""
    paras = OBJ + [SED, RESP] + REPLIES + [B("Reply to Objection 4:", "Augustine means x.")]
    corrections = {"paragraphs": {"FP_Q1_A1-p9": {
        "role": "reply", "targets": ["sc 1"], "latin": ["I q. 13 a. 10 ad 4 [CT 1]"]}},
        "articles": {}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections)
    reply = doc.passages[-1]
    assert reply.unit_label == "Reply to Objection 4"
    assert reply.metadata["reply_targets"] == ["sc 1"] and ", ad 4: " in reply.reference
    assert not content.summa_reply_targets([doc], corrections)


def test_reply_past_the_last_objection_answers_a_sed_contra(tmp_path):
    """Where R7's file records nothing (the Supplement), a reply numbered past the last
    objection answers the sed contra arguments in order (XP q.69 a.3)."""
    paras = OBJ + [SED, "Further, Jerome argues so.", RESP] + REPLIES + [
        B("Reply to Objection 4:", "Jerome speaks of glory."),
        B("Reply to Objection 5:", "There is no parity.")]
    doc = _build(tmp_path, _xml(_article("XP_Q1_A1", paras), part="XP",
                                part_title="Supplement"))
    assert [p.metadata["reply_targets"] for p in doc.passages[-2:]] == [["sc 1"], ["sc 2"]]
    assert not content.summa_reply_targets([doc], NO_CORRECTIONS)


def test_reply_only_article_gets_no_determination(tmp_path):
    """I q.74 a.3 and q.91 a.4: the Latin has no determination, so none is invented."""
    paras = OBJ + [SED] + REPLIES
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert "I answer that" not in _labels(doc)
    assert structure.summa_reply_only([doc], {"FP_Q1_A1"}) == {}
    assert structure.summa_reply_only([doc], set()) == {
        "structure.summa.reply-only-articles:summa": ["missing:FP_Q1_A1"]}


def test_recovered_unit_in_place(tmp_path):
    """A whole unit CCEL lost is its own passage, in place (`recovered-<n>`); text lost
    inside a kept paragraph goes back inside it, which keeps its anchor (D1), and a
    determination that opened there becomes its own part (`-2`)."""
    paras = OBJ[:2] + [B("Objection 3:", "Further, the genus is from the matter."),
                       B("On the contrary,", "Dionysius says that every enlightenment to "
                         "the superior angels is so."), REPLIES[0]]
    recovered = {
        "editions": {"dom2-v4": {"archive": "x", "edition": "Second edition (1922)"}},
        "units": [{"article": "FP_Q1_A1", "unit": "obj 3", "after": "FP_Q1_A1-p2",
                   "source": "dom2-v4", "page": "35", "leaf": 47,
                   "text": "Further, the embryo is an animal before it is a man."}],
        "in_place": [{"paragraph": "FP_Q1_A1-p4", "source": "dom2-v4", "page": "180",
                      "find": "every enlightenment to the superior angels",
                      "replace": "every enlightenment is borne by angels. I answer that, "
                                 "The inferior angels can speak to the superior angels",
                      "parts": [{"opens_with": "On the contrary,", "role": "sed-contra"},
                                {"opens_with": "I answer that,", "role": "determination",
                                 "anchor_suffix": "-2"}]}]}
    corrections = {"paragraphs": {"FP_Q1_A1-p3": {"role": "objection", "number": 4}},
                   "articles": {}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections, recovered)
    by_anchor = {p.anchor: p for p in doc.passages}
    unit = by_anchor["summa/FP_Q1_A1/recovered-1"]
    assert unit.unit_label == "Objection 3" and unit.voice == "rejected"
    assert unit.metadata["recovered_from"] == "Second edition (1922), p. 35"
    assert by_anchor["summa/FP_Q1_A1/p3"].unit_label == "Objection 4"
    assert [p.anchor for p in doc.passages][:4] == [
        "summa/FP_Q1_A1/p1", "summa/FP_Q1_A1/p2", "summa/FP_Q1_A1/recovered-1",
        "summa/FP_Q1_A1/p3"]
    assert by_anchor["summa/FP_Q1_A1/p4"].content.endswith("is borne by angels.")
    determination = by_anchor["summa/FP_Q1_A1/p4-2"]
    assert determination.unit_label == "I answer that"
    assert determination.content.startswith("I answer that, The inferior angels")


def test_duplicate_sed_contra_once(tmp_path):
    """I-II q.20 a.6 prints its sed contra twice; the second copy is not built."""
    paras = OBJ + [SED, SED, RESP]
    corrections = {"paragraphs": {"FP_Q1_A1-p5": {"role": "duplicate",
                                                  "duplicate_of": "FP_Q1_A1-p4"}},
                   "articles": {}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections)
    assert [p.unit_label for p in doc.passages].count("On the contrary") == 1
    assert not content.summa_adjacent_duplicates([doc])


def test_objection_voice_rejected(tmp_path):
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", OBJ + [SED, RESP] + REPLIES)))
    assert {p.unit_label.split()[0]: p.voice for p in doc.passages} == {
        "Objection": "rejected", "On": None, "I": None, "Reply": None}


def test_text_as_printed_keeps_the_openings(tmp_path):
    """C-27: "On the contrary," and "I answer that," stay at the start of their part."""
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", OBJ + [SED, RESP])))
    assert doc.passages[3].content.startswith("On the contrary, Augustine")
    assert doc.passages[4].content.startswith("I answer that, It is so")
    assert doc.passages[0].content.startswith("It would seem")


def test_letterless_part_is_dropped_and_recorded(tmp_path):
    """III q.16 a.3: a translator's note before the objections leaves only "." after the
    apparatus strip; the part is dropped and recorded for the release report."""
    paras = ["[*The question is hardly apposite in English.] ."] + OBJ + [SED, RESP]
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert doc.passages[0].unit_label == "Objection 1"
    assert doc.passages[0].anchor == "summa/FP_Q1_A1/p2"
    assert doc.metadata["dropped_empty_parts"] == ["FP_Q1_A1-p1"]


# --------------------------------------------------------------------------- questions

def test_question_prologue_before_article_1(tmp_path):
    prologue = ('<p id="FP_Q1-p1"></p><p id="FP_Q1-p2">To place our purpose within proper '
                'limits, we first investigate this doctrine.</p>'
                '<p id="FP_Q1-p3">(1) Whether it is necessary?</p>')
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", OBJ + [SED, RESP]), prologue=prologue))
    first = doc.passages[0]
    assert (first.unit_label, first.anchor) == ("Question 1, prologue", "summa/FP_Q1/p2")
    assert first.reference == "Summa Theologiae I, q. 1, prologue"
    assert first.chapter_key.endswith("/prologue")
    assert "Whether it is necessary?" in first.content
    assert "article" not in first.metadata
    assert doc.passages[1].chapter_key != first.chapter_key


def test_single_article_question(tmp_path):
    """I q.71: the article sits in the div3 with no div4. Its opening sentence is the
    question's prologue; the rest is article 1."""
    paras = "".join(f'<p id="FP_Q71-p{k}">{t}</p>' for k, t in enumerate(
        ["We must next consider the work of the fifth day."] + OBJ + [SED, RESP], 1))
    xml = (f'<ThML><ThML.body><div1 title="First Part" id="FP"><div2 title="T" id="FP.i">'
           f'<div3 title="Question. 71 - ON THE WORK OF THE FIFTH DAY (ONE ARTICLE)" '
           f'id="FP_Q71">{paras}</div3></div2></div1></ThML.body></ThML>')
    doc = _build(tmp_path, xml)
    prologue, *article = doc.passages
    assert prologue.unit_label == "Question 71, prologue"
    assert {p.chapter_key for p in article} == {
        "summa/first-part/question-71-on-the-work-of-the-fifth-day-one-article/article-1"}
    assert article[0].reference == ("Summa Theologiae I, q. 71, a. 1, obj. 1: "
                                    "On the Work of the Fifth Day")
    assert {p.metadata["article"] for p in article} == {"FP_Q71"}


def test_treatise_prologue(tmp_path):
    xml = ('<ThML><ThML.body><div1 title="Third Part" id="TP">'
           '<div2 title="Prologue" id="TP.i"><p id="TP.i-p1">Forasmuch as our Saviour '
           'showed us the way of truth.</p></div2>'
           '<div2 title="EDITOR\'S NOTE:" id="XP.i"><p id="XP.i-p1">After writing these '
           'questions St. Thomas died.</p></div2></div1></ThML.body></ThML>')
    doc = _build(tmp_path, xml)
    assert [(p.unit_label, p.reference) for p in doc.passages] == [
        ("Prologue", "Summa Theologiae III, prologue")]


def test_article_number_comes_from_the_div_id(tmp_path):
    """I q.114 a.5 is titled "Article. 4"; the id wins there. Any other disagreement
    fails the build."""
    xml = _xml(_article("FP_Q114_A5", OBJ + [SED, RESP],
                        title="Article. 4 - Whether a demon who is overcome is hindered?"),
               question="Q114", q_title="Question. 114 - OF THE ASSAULTS (FIVE ARTICLES)")
    doc = _build(tmp_path, xml)
    assert "Article 5 - Whether a demon" in doc.passages[0].chapter_label
    assert ", a. 5, " in doc.passages[0].reference
    bad = _xml(_article("FP_Q1_A2", OBJ + [SED, RESP], title="Article. 3 - Whether x?"))
    with pytest.raises(ValueError, match="FP_Q1_A2"):
        _build(tmp_path, bad)


# --------------------------------------------------------------------------- citations

def test_citation_format():
    assert summa._citation("SS_Q83_A14", "Reply to Objection 2") == \
        "Summa Theologiae II-II, q. 83, a. 14, ad 2"
    assert summa._citation("FP_Q29_A2", "Objection 4") == "Summa Theologiae I, q. 29, a. 2, obj. 4"
    assert summa._citation("FS_Q1_A1", "On the contrary") == \
        "Summa Theologiae I-II, q. 1, a. 1, sed contra"
    assert summa._citation("TP_Q1_A1", "I answer that") == "Summa Theologiae III, q. 1, a. 1, co."
    assert summa._citation("XP_Q1_A1", "Reply to Objections 2 and 3") == \
        "Summa Theologiae Suppl., q. 1, a. 1, ad 2 and 3"
    assert summa._citation("AP1_Q1_A1", "I answer that") == \
        "Summa Theologiae Suppl., App. 1, q. 1, a. 1, co."
    assert summa._citation("FP_Q2", "Question 2, prologue") == "Summa Theologiae I, q. 2, prologue"
    assert summa._citation("FS.i.i", "Prologue") == "Summa Theologiae I-II, prologue"


def test_citation_keeps_question(tmp_path):
    doc = _build(tmp_path, _xml(_article(
        "SS_Q64_A6", OBJ + [SED, RESP], title="Article. 6 - Whether it is lawful to kill the "
        "innocent?"), part="SS", part_title="Second Part of the Second Part",
        question="Q64", q_title="Question. 64 - OF MURDER (EIGHT ARTICLES)"))
    assert doc.passages[-1].reference == ("Summa Theologiae II-II, q. 64, a. 6, co.: "
                                          "Whether it is lawful to kill the innocent?")
    assert not content.summa_reference_has_question([doc])


def test_split_part_uses_piece_reference_suffix(tmp_path):
    """A part longer than a card is packed from its paragraphs (1.10c); each piece cites
    "(part k of n)" after the article's question (D5)."""
    long = "Now this is a sentence of a long determination. " * 40
    resp = [B("I answer that,", long)] + [long] * 5
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", OBJ + [SED] + resp)))
    pieces = [p for p in doc.passages if p.unit_label == "I answer that"]
    n = len(pieces)
    assert n > 2
    assert pieces[0].reference == ("Summa Theologiae I, q. 1, a. 1, co.: Whether it is so? "
                                   f"(part 1 of {n})")
    assert pieces[-1].reference.endswith(f"(part {n} of {n})")
    assert [p.anchor for p in pieces][0] == "summa/FP_Q1_A1/p5"
    assert all(p.anchor.startswith("summa/FP_Q1_A1/p5/from-p") for p in pieces[1:])
    assert len({p.reference for p in doc.passages}) == len(doc.passages)


# --------------------------------------------------------------------------- checks

def _article_with_missing_reply_target(tmp_path, note: bool):
    paras = OBJ[:2] + [B("Objection 3:", "Further, the genus is from the matter."), SED,
                       RESP, REPLIES[0], REPLIES[1], B("Reply to Objection 4:", "x.")]
    corrections = {"paragraphs": {"FP_Q1_A1-p3": {"role": "objection", "number": 4}},
                   "articles": {"FP_Q1_A1": {"missing": [
                       {"unit": "obj 3", "missing": True, "after": "FP_Q1_A1-p2",
                        "latin": "I q. 1 a. 1 arg. 3 [CT 1]", "defect": "ccel"}]}}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections)
    # The reply to objection 3, which no edition restores, keeps its target (R7).
    reply = next(p for p in doc.passages if p.unit_label == "Reply to Objection 2")
    reply.metadata["reply_targets"] = ["obj 3"]
    doc.passages[0].note = "The English translation omits part of this article." if note \
        else None
    return doc, corrections


def test_reply_to_documented_missing_unit_passes_with_note(tmp_path):
    doc, corrections = _article_with_missing_reply_target(tmp_path, note=True)
    assert not content.summa_reply_targets([doc], corrections)
    doc, corrections = _article_with_missing_reply_target(tmp_path, note=False)
    assert content.summa_reply_targets([doc], corrections) == {
        "context.summa.reply-targets:summa": ["summa/FP_Q1_A1/p7:obj 3"]}


def test_reply_to_recovered_unit_resolves(tmp_path):
    paras = OBJ[:2] + [B("Objection 3:", "Further, the genus."), SED, RESP] + REPLIES + [
        B("Reply to Objection 4:", "The genus is not from the matter.")]
    recovered = {"editions": {"e": {"archive": "x", "edition": "E"}}, "in_place": [],
                 "units": [{"article": "FP_Q1_A1", "unit": "obj 3", "after": "FP_Q1_A1-p2",
                            "source": "e", "page": "1", "leaf": 1, "text": "Further, x."}]}
    corrections = {"paragraphs": {"FP_Q1_A1-p3": {"role": "objection", "number": 4}},
                   "articles": {}}
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)), corrections, recovered)
    assert not content.summa_reply_targets([doc], corrections)
    assert not structure.summa_argument_numbering([doc])


def test_argument_numbering_check(tmp_path):
    paras = [OBJ[0], OBJ[2], SED, RESP]
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", paras)))
    assert structure.summa_argument_numbering([doc]) == {
        "structure.summa.argument-numbering:summa": ["FP_Q1_A1"]}


def test_unbold_opening_check_catches_an_absorbed_part(tmp_path):
    doc = _build(tmp_path, _xml(_article("FP_Q1_A1", OBJ + [SED, RESP])))
    doc.passages[2].content += "\n\nOn the contrary, Augustine says so."
    assert content.summa_unbold_openings([doc]) == {
        "roles.summa.unbold-paragraph-openings:summa": [doc.passages[2].anchor]}


# --------------------------------------------------------------------------- the files

def test_recovered_file_holds_only_edition_text_with_its_page():
    recovered = json.load(open(summa.RECOVERED, encoding="utf-8"))
    corrections = json.load(open(summa.CORRECTIONS, encoding="utf-8"))
    for unit in recovered["units"]:
        assert unit["source"] in recovered["editions"] and unit["page"] and unit["text"]
        missing = corrections["articles"][unit["article"]]["missing"]
        assert any(m["unit"] == unit["unit"] and m["after"] == unit["after"] for m in missing)
    for fix in recovered["in_place"]:
        assert fix["source"] in recovered["editions"] and fix["page"]
        if fix["paragraph"] == "TP_Q7_A5-p6":
            continue                    # a misprint corrected ("a[9]" for "as")
        # A restoration adds the printed words; it keeps every word CCEL has.
        rest = iter(fix["replace"].split())
        assert all(word in rest for word in fix["find"].split()), fix["paragraph"]


# --------------------------------------------------------------------------- source

@pytest.fixture(scope="module")
def built():
    return build_document(_SRC)


@pytest.mark.sources
@_needs_sources
def test_summa_builds_one_document_with_clean_refs(built):
    assert built.collection == "summa"
    limit = settings.MAX_PASSAGE_CHARS + DISPLAY_PASSAGE_MAX_OVERSHOOT
    assert all(len(p.content) <= limit for p in built.passages)
    assert not any("Q[" in p.reference or "A[" in p.reference for p in built.passages)


@pytest.mark.sources
@_needs_sources
def test_source_checks(built):
    """1.7's source checks: Q71 and Q72 exist; I q.114 runs a.1 to a.5; no piece under 20
    characters; only the reply-only articles lack a determination; references are unique
    and keep their question; every Summa check passes."""
    articles = structure.summa_articles_built([built])
    for q in ("FP_Q71", "FP_Q72"):
        assert q in articles
    q114 = sorted({p.metadata["article"] for p in built.passages
                   if (p.metadata.get("article") or "").startswith("FP_Q114_")})
    assert q114 == [f"FP_Q114_A{n}" for n in range(1, 6)]
    labels = {p.chapter_label for p in built.passages if p.metadata.get("article") in q114}
    assert len({re.search(r"Article (\d+)", lab)[1] for lab in labels}) == 5
    assert not [p.anchor for p in built.passages if len(p.content) < 20]
    corrections = json.load(open(summa.CORRECTIONS, encoding="utf-8"))
    reply_only = {a for a, f in corrections["articles"].items() if f.get("reply_only")}
    assert reply_only == {"FP_Q74_A3", "FP_Q91_A4"}
    assert content.run("summa", [built], corrections=corrections, works=[]) == {}
    assert structure.run("summa", [built], corrections=corrections) == {}
    assert max(Counter(p.reference for p in built.passages).values()) == 1


@pytest.mark.sources
@_needs_sources
def test_source_prologues_and_recovered_units(built):
    prologues = [p for p in built.passages if (p.unit_label or "").endswith("prologue")]
    assert len({p.chapter_key for p in prologues}) == 613
    treatises = [p.reference for p in built.passages if p.unit_label == "Prologue"]
    assert treatises == ["Summa Theologiae I-II, prologue", "Summa Theologiae III, prologue"]
    recovered = [p for p in built.passages if "/recovered-" in p.anchor]
    assert len(recovered) == 8 and all(p.metadata["recovered_from"] for p in recovered)
    note = [p for p in built.passages if p.note]
    assert [p.metadata["article"] for p in note] == ["SS_Q20_A3"]
    excluded = {e["paragraph"] for e in built.metadata["excluded_paragraphs"]}
    assert summa.OUTSIDE_LEONINE <= excluded
    assert "TP_Q55_A6-p6" not in excluded
