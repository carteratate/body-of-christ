"""0.1d's checks for the 6 Oct 2026 corpus reviews. Runs in CI: every document and source
file is written here, with made-up text, and no vendored source is read. Each rule and
check fires on a crafted bad case and stays silent on a good one."""
import hashlib
import json

import pytest

import health
from checks import content, report, structure, unit_coverage
from checks.coverage import match_key, split_sentences
from checks.source_text import SourceUnit, usfm_units
from checks import sequence as seq
from model import Document, Passage, Work
from release import outline

PROSE = "The light shines in the darkness, and the darkness has never overcome it at all."


def _p(content=PROSE, anchor="a", position=0, reference=None, chapter_key="ch-1",
       chapter_label="Chapter 1", unit_label=None, metadata=None, work_key=None,
       passage_author=None):
    return Passage(content=content, reference=anchor if reference is None else reference,
                   anchor=anchor, chapter_key=chapter_key, chapter_label=chapter_label,
                   position=position, unit_label=unit_label, metadata=metadata,
                   work_key=work_key, passage_author=passage_author)


def _doc(*passages, collection="encyclicals", doc_id="doc-1", title="A Document",
         author=None, metadata=None, works=()):
    for i, p in enumerate(passages):
        p.position = i
    return Document(id=doc_id, collection=collection, title=title, author=author,
                    metadata=metadata, passages=list(passages), works=list(works))


def _rules(document):
    return [v.rule for v in health.check_documents(document.collection, [document])]


# --------------------------------------------------------------------------- health

def test_r9_trailing_heading():
    bad = _doc(_p(PROSE + "\n\nDark Clouds Over a Closed World", anchor="a"), _p(anchor="b"))
    [v] = [v for v in health.check_documents("encyclicals", [bad])
           if v.rule == "R9_trailing_heading"]
    assert v.severity == "block"       # since 1.3a
    # A last line with final punctuation, a passage with one line, the last passage, and
    # a collection outside the papal three are silent.
    for good in (_doc(_p(PROSE + "\n\nAnd so it ends.", anchor="a"), _p(anchor="b")),
                 _doc(_p("Dark Clouds Over a Closed World", anchor="a"), _p(anchor="b")),
                 _doc(_p(anchor="a"), _p(PROSE + "\n\nDark Clouds", anchor="b")),
                 _doc(_p(PROSE + "\n\nDark Clouds", anchor="a"), _p(anchor="b"),
                      collection="summa")):
        assert "R9_trailing_heading" not in _rules(good)


def test_r10_site_boilerplate_blocks():
    bad = _doc(_p(PROSE + " Subscribe for a membership today.", anchor="a"),
               collection="councils")
    [v] = [v for v in health.check_documents("councils", [bad]) if v.rule == "R10_site_boilerplate"]
    assert v.severity == "block"
    with pytest.raises(ValueError, match="R10_site_boilerplate"):
        health.refuse_block_violations("councils", [bad], known=set())
    health.refuse_block_violations("councils", [bad], known={v.check_id})
    assert "R10_site_boilerplate" not in _rules(_doc(_p(anchor="a"), collection="councils"))


def test_r11_papal_editorial():
    for text in ("This Exhortation, which the Holy Father addressed to the clergy.",
                 "Translation by the News Service.", "Living in justice [24-25] 2. Order"):
        assert "R11_papal_editorial" in _rules(_doc(_p(text))), text
    assert "R11_papal_editorial" not in _rules(_doc(_p("As in §§24-25 above, we said.")))
    assert "R11_papal_editorial" not in _rules(
        _doc(_p("Translation by the News Service."), collection="church-fathers"))


@pytest.mark.parametrize("text", [
    "the imitation of her virtues.(35) She is",
    "Catherine of Siena,6 who said",
    "the work of ecumenism. 7 In indicating this",
    "as we said [ 3 ] before",
    "the Virgin Mary.(1*) This mystery",
])
def test_r12_note_caller(text):
    assert "R12_note_caller" in _rules(_doc(_p(text)))


@pytest.mark.parametrize("text", [
    "as it is written in Rom. i. 17 But what follows",    # a Scripture citation
    "the people of God. 1 Peter speaks of this",           # a number before a book
    "as John 3:16. 2 And then",                             # chapter and verse
    "she sinneth not.” Ver. 28 Hence it is",                 # a verse in the same chapter
    "the depths tremble. 4 Esdr. iii. 8. Thou art",          # a number before a book
    "the Cross (AAS [39] 1947, 552, 553). We",               # an AAS citation's volume
])
def test_r12_skips_citations(text):
    assert "R12_note_caller" not in _rules(_doc(_p(text)))


def test_r12_skips_bible_canon_law_and_summa():
    for collection in ("bible", "canon-law", "summa"):
        assert "R12_note_caller" not in _rules(_doc(_p("virtues.(35) She"), collection=collection))


def test_r13_lower_start():
    assert "R13_lower_start" in _rules(_doc(_p("stands the authority of Scripture.")))
    assert "R13_lower_start" not in _rules(_doc(_p()))


def test_r14_hyphen_space_and_allowlist(monkeypatch):
    assert "R14_hyphen_space" in _rules(_doc(_p("we be- seech you")))
    assert "R14_hyphen_space" not in _rules(_doc(_p("we beseech you - all of you")))
    patterns = json.loads(json.dumps(health.load_patterns()))
    patterns["R14_hyphen_space"]["allowed"] = ["be- seech"]
    monkeypatch.setattr(health, "load_patterns", lambda path=None: patterns)
    assert "R14_hyphen_space" not in _rules(_doc(_p("we be- seech you")))


def test_no_ligatures_in_content_and_labels():
    assert "no_ligatures" in _rules(_doc(_p("the æons of the heretics")))
    assert "no_ligatures" in _rules(_doc(_p(), title="Of the Manichæans"))
    assert "no_ligatures" not in _rules(_doc(_p("the aeons of the heretics")))


def test_summa_bracket_numbers():
    assert "summa_bracket_numbers" in _rules(_doc(_p("De Anima iii, 21,[22]."), collection="summa"))
    assert "summa_bracket_numbers" not in _rules(_doc(_p("De Anima iii, 21, 22."), collection="summa"))


def test_tracked_rules_group_by_document():
    document = _doc(_p(PROSE + " Holy Father addressed them.", anchor="a"),
                    _p("the æons", anchor="b"), _p(anchor="c"), title="Of the Manichæans")
    ids = health.tracked_check_ids(health.check_documents("encyclicals", [document]))
    assert ids == {"health.R11_papal_editorial:encyclicals/doc-1": ["a"],
                   "health.no_ligatures:encyclicals/doc-1": ["b", "(document)"]}
    # Untracked report rules (R13, R14) are never grouped into a check.
    assert not any("R13" in k or "R14" in k for k in ids)


# --------------------------------------------------------------------------- structure

def test_chapter_contiguous():
    bad = _doc(_p(anchor="a", chapter_key="k1"), _p(anchor="b", chapter_key="k2"),
               _p(anchor="c", chapter_key="k1"), collection="canon-law")
    assert structure.chapter_contiguous("canon-law", [bad]) == {
        "structure.chapter_contiguous:canon-law": ["k1"]}
    good = _doc(_p(anchor="a", chapter_key="k1"), _p(anchor="b", chapter_key="k1"),
                _p(anchor="c", chapter_key="k2"), collection="canon-law")
    assert structure.chapter_contiguous("canon-law", [good]) == {}


def _canon_sources(tmp_path):
    base = tmp_path / "canon-law"
    base.mkdir()
    (base / "pages.json").write_text(json.dumps([
        {"file": "cic_index_en.html", "parsed": False}, {"file": "cic_lib7-cann1-9_en.html"}]))
    link = "/archive/eng/documents/cic_lib7-cann1-9_en.html"
    (base / "cic_index_en.html").write_text(
        f'<a href="{link}#TITLE_I.">TITLE I. ONE</a>'
        f'<a href="{link}#CHAPTER_I.">CHAPTER I. FIRST</a>'
        f'<a href="{link}#CHAPTER_II.">CHAPTER II. SECOND</a>'
        f'<a href="{link}#TITLE_II.">TITLE II. TWO</a>'
        f'<a href="{link}#CHAPTER_I.">CHAPTER I. AGAIN</a>')
    # The body's second CHAPTER_II anchor drops its full stop, as one vendored page does.
    (base / "cic_lib7-cann1-9_en.html").write_text(
        '<a name="TITLE_I.">TITLE I.</a><a name="CHAPTER_I.">CHAPTER I.</a>'
        "<p>Can. 1 One.</p><a name=\"CHAPTER_II\">CHAPTER II.</a><p>Can.&nbsp;2 Two.</p>"
        '<a name="TITLE_II.">TITLE II.</a><p>Can. 3 Three.</p>'
        '<a name="CHAPTER_I.">CHAPTER I.</a><p>Can. 4 Four.</p>')
    return str(tmp_path)


def test_canon_chapters_follow_the_table_of_contents(tmp_path):
    chapters = structure.canon_chapters(_canon_sources(tmp_path))
    # Canon 3 sits under a title with no chapter: a higher heading resets the lower ones.
    assert chapters == {1: "I", 2: "II", 4: "I"}


def test_canon_chapter_number_agreement(tmp_path):
    chapters = structure.canon_chapters(_canon_sources(tmp_path))
    built = _doc(*[_p(anchor=f"can/{n}", metadata={"canon": n, "chapter": label})
                   for n, label in ((1, "Chapter I"), (2, "Chapter I"), (3, "Chapter I"),
                                    (4, ""))], collection="canon-law")
    assert structure.canon_chapter_number_agreement([built], chapters) == {
        "structure.canon_law.chapter_number_agreement:canon-law": ["2"]}


def test_chapter_sequence():
    def vat2(*labels):
        return _doc(*[_p(anchor=str(i), chapter_label=l, chapter_key=str(i))
                      for i, l in enumerate(labels)], collection="councils",
                    metadata={"source_key": "councils/vat2-x"})
    assert structure.chapter_sequence("councils", [vat2("Chapter I", "Chapter II", "Chapter IV")]) \
        == {"structure.chapter_sequence:councils/doc-1": ["gap:II-IV"]}
    assert structure.chapter_sequence("councils", [vat2("Chapter I", "Chapter II", "Chapter I")]) \
        == {"structure.chapter_sequence:councils/doc-1": ["repeat:I"]}
    assert structure.chapter_sequence("councils", [vat2("Preface", "Chapter I", "Chapter II")]) == {}
    other = vat2("Chapter I", "Chapter III")
    other.metadata = {"source_key": "councils/ecum-19-council-of-trent"}
    assert structure.chapter_sequence("councils", [other]) == {}


def _units(*items):
    return [SourceUnit("f.html", uid, text, region) for uid, text, region in items]


def test_bucket_chapters_with_headings():
    headed = _units(("1", PROSE, "body"), (None, "The Priest and Prayer", "body"),
                    ("2", PROSE, "body"))
    plain = _units(("1", PROSE, "body"), (None, PROSE, "body"), ("2", PROSE, "body"))
    assert structure.source_has_headings(headed) and not structure.source_has_headings(plain)
    bucketed = _doc(_p(chapter_label="Paragraphs 1–2"))
    titled = _doc(_p(chapter_label="The Priest and Prayer"), doc_id="doc-2")
    assert structure.bucket_chapters_with_headings(
        "encyclicals", {"f.html": [bucketed, titled]}, {"f.html": headed}) == {
        "structure.bucket_chapters_with_headings:encyclicals": ["doc-1"]}
    assert structure.bucket_chapters_with_headings(
        "encyclicals", {"f.html": [bucketed]}, {"f.html": plain}) == {}


def _syllabus(*passages):
    return _doc(*passages, metadata={"source_key": "encyclicals/syllabus-of-errors"})


def test_syllabus_body_boundary():
    after = "An extract from another document, which the source prints after the list."
    units = _units(*[(str(n), f"Proposition number {n} is condemned in this list.", "body")
                     for n in range(1, 81)], (None, after, "body"))
    good = _syllabus(*[_p(f"Proposition number {n} is condemned in this list.", anchor=str(n),
                          reference=f"Syllabus, §{n}") for n in range(1, 81)])
    assert structure.syllabus_body_boundary([good], units) == {}
    bad = _syllabus(*[_p(f"Proposition number {n} is condemned in this list."
                         + (" " + after if n == 80 else ""), anchor=str(n),
                         reference=f"Syllabus, §{n}") for n in range(1, 81)])
    assert structure.syllabus_body_boundary([bad], units) == {
        "structure.syllabus_body_boundary:encyclicals": ["after-80"]}
    short = _syllabus(*[_p(anchor=str(n), reference=f"Syllabus, §{n}") for n in range(1, 80)])
    assert structure.syllabus_body_boundary([short], units)[
        "structure.syllabus_body_boundary:encyclicals"] == ["propositions:79"]


def _article(div, *labels, key=None):
    return [_p(anchor=f"summa/{div}/p{i + 2}", chapter_key=key or div, unit_label=label)
            for i, label in enumerate(labels)]


SINGLE = ("Objection 1", "Objection 2", "On the contrary", "I answer that",
          "Reply to Objection 1", "Reply to Objection 2")


def test_summa_one_disputation_per_article():
    good = _doc(*_article("SS_Q1_A1", *SINGLE), collection="summa")
    assert structure.summa_one_disputation([good], set()) == {}
    double = _doc(*_article("SS_Q64_A7", *SINGLE, *SINGLE), collection="summa")
    no_answer = _doc(*_article("FP_Q117_A2", "Objection 1", "On the contrary",
                               "Reply to Objection 1"), collection="summa")
    reply_only = _doc(*_article("FP_Q74_A3", "Objection 1", "Reply to Objection 1"),
                      collection="summa")
    out = structure.summa_one_disputation([double, no_answer, reply_only], {"FP_Q74_A3"})
    assert out == {"structure.summa.one-disputation-per-article:summa": ["SS_Q64_A7", "FP_Q117_A2"]}


def test_reply_only_articles_come_from_r7():
    corrections = {"articles": {"FP_Q74_A3": {"reply_only": True}, "FP_Q117_A2": {
        "not_reply_only": "R7"}}}
    assert structure.reply_only_articles(corrections) == {"FP_Q74_A3"}


def test_embedded_work_labelled():
    chapters = ["Book I · Chap. I", "Book I · Chap. II", "Chap. I", "Chap. II", "Chap. III"]
    bad = _doc(*[_p(anchor=f"c{i}", chapter_key=f"c{i}", chapter_label=l)
                 for i, l in enumerate(chapters)], collection="church-fathers")
    assert structure.embedded_work_labelled("church-fathers", [bad]) == {
        "structure.embedded_work_labelled:church-fathers/doc-1": ["c2"]}
    worked = _doc(*[_p(anchor=f"c{i}", chapter_key=f"c{i}", chapter_label=l,
                       work_key="epitome" if i >= 2 else None)
                    for i, l in enumerate(chapters)], collection="church-fathers")
    short = _doc(*[_p(anchor=f"c{i}", chapter_key=f"c{i}", chapter_label=l)
                   for i, l in enumerate(chapters[:4])], collection="church-fathers")
    assert structure.embedded_work_labelled("church-fathers", [worked, short]) == {}


def test_large_chapters_is_report_only():
    big = _doc(_p("x" * 30_000, anchor="a"), _p("x" * 30_000, anchor="b"),
               _p("short", anchor="c", chapter_key="ch-2"))
    rows = structure.large_chapters("encyclicals", [big])
    assert [(r["chapter_key"], r["characters"], r["passages"]) for r in rows] == [("ch-1", 60_000, 2)]
    assert structure.run("encyclicals", [big]) == {}


# --------------------------------------------------------------------------- content

def test_summa_objection_after_replies():
    bad = _doc(*_article("SS_Q172_A1", "Objection 1", "On the contrary", "I answer that",
                         "Reply to Objection 1", "Objection 2"), collection="summa")
    assert content.summa_objection_after_replies([bad]) == {
        "roles.summa.objection-after-replies:summa": ["summa/SS_Q172_A1/p6"]}
    # A second article in one div restarts at Objection 1: one-disputation's to report.
    double = _doc(*_article("SS_Q64_A7", *SINGLE, *SINGLE), collection="summa")
    assert content.summa_objection_after_replies([double]) == {}


def test_summa_sed_contra_boundaries():
    corrections = {"paragraphs": {"FS_Q46_A7-p5": {"role": "sed-contra"},
                                  "FS_Q7_A3-p5": {"role": "sed-contra"},
                                  "FP_Q29_A2-p5": {"latin_role": "sed-contra"}}}
    folded = _doc(_p(anchor="summa/FS_Q46_A7/p4", unit_label="Objection 3"),
                  _p(anchor="summa/FS_Q7_A3/p5", unit_label="On the contrary"),
                  _p(anchor="summa/FP_Q29_A2/p5", unit_label="Objection 4"), collection="summa")
    assert content.summa_sed_contra_boundaries([folded], corrections) == {
        "roles.summa.variant-sed-contra-boundaries:summa": ["FS_Q46_A7-p5"]}
    separate = _doc(_p(anchor="summa/FS_Q46_A7/p5", unit_label="On the contrary"),
                    _p(anchor="summa/FS_Q7_A3/p5", unit_label="On the contrary"),
                    collection="summa")
    assert content.summa_sed_contra_boundaries([separate], corrections) == {}


def test_summa_adjacent_duplicates():
    bad = _doc(_p(anchor="a"), _p(anchor="b"), collection="summa")
    assert content.summa_adjacent_duplicates([bad]) == {
        "text.summa.adjacent-duplicate-parts:summa": ["b"]}
    other_article = _doc(_p(anchor="a"), _p(anchor="b", chapter_key="ch-2"), collection="summa")
    assert content.summa_adjacent_duplicates([other_article]) == {}


def test_argument_lines():
    bad = _doc(_p("Argument.—The Clergy Had Learnt This.\n\n" + PROSE, anchor="a"),
               _p("Chapter V.—Argument: Caecilius Begins.", anchor="b"), _p(anchor="c"),
               collection="church-fathers")
    assert content.argument_lines("church-fathers", [bad]) == {
        "editorial.argument_lines:church-fathers/doc-1": ["a", "b"]}
    refutation = _doc(_p("Argument.—Summary of the book."), collection="church-fathers",
                      metadata={"source_key": "church-fathers/third-century-2.xml#iii.iii"})
    assert content.argument_lines("church-fathers", [refutation]) == {}


def test_chapter_title_lines():
    key = {"source_key": "church-fathers/third-century.xml#iii.v"}
    bad = _doc(_p("Chapter I.—Of Marriage.\n\n" + PROSE, anchor="a"), _p(anchor="b"),
               _p("Chapter II.—Argument: a summary.", anchor="c"),
               collection="church-fathers", metadata=key)
    assert content.chapter_title_lines("church-fathers", [bad]) == {
        "editorial.chapter_title_lines:church-fathers/doc-1": ["a"]}
    city_of_god = _doc(_p("Chapter I.—Of the Enemies of the Name of Christ.\n\n" + PROSE),
                       collection="church-fathers",
                       metadata={"source_key": "church-fathers/city-of-god.xml#iv"})
    assert content.chapter_title_lines("church-fathers", [city_of_god]) == {}


def test_provenance_lines():
    bad = _doc(_p("On Luke. Mai, Script. vet. collectio nova, vol. ix. p. 645, Rome, 1837.\n\n"
                  + PROSE, anchor="a"),
               _p("II. Apud. Gretserum, De Sancta Cruce, tom. ii. p. 403.", anchor="b"),
               collection="church-fathers")
    assert content.provenance_lines("church-fathers", [bad]) == {
        "editorial.provenance_lines:church-fathers/doc-1": ["a", "b"]}
    good = _doc(_p("[Mai, Script. vet., vol. ix. p. 645.]", anchor="a"),
                _p("Respecting these lines, Miller refers us to Fabricius, vol. ii. p. 3.",
                   anchor="b"), collection="church-fathers")
    assert content.provenance_lines("church-fathers", [good]) == {}


def _letter(n, title, greeting, key, **kw):
    return _p(f"Epistle {n}. Oxford ed.: Ep. {n.lower()}.\n\n{title}\n\nArgument.—A summary.\n\n"
              f"1. {greeting} greeting. {PROSE}", anchor=key, chapter_key=key,
              chapter_label=f"Epistle {n}", **kw)


def test_letter_sender():
    letters = [_letter("I", "To the Presbyters.", "Cyprian to the presbyters,", "e1"),
               _letter("II", "Cornelius to Cyprian, on the Confessors.", "Cornelius to Cyprian,", "e2"),
               _letter("III", "Cyprian to the Lapsed.", "Our Lord says,", "e3"),
               _letter("IV", "Caecilius, on the Cup.", "Cyprian to Caecilius,", "e4")]
    document = _doc(*letters, collection="church-fathers", title="The Epistles of Cyprian.",
                    author="Cyprian.")
    assert content.letter_senders("church-fathers", [document]) == {
        "attribution.letter_sender:church-fathers/doc-1": ["e2"]}
    letters[1].passage_author = "Cornelius of Rome"
    assert content.letter_senders("church-fathers", [document]) == {}
    worked = _doc(_letter("II", "Firmilian, Bishop of Caesarea, to Cyprian.", "Firmilianus to Cyprian,",
                          "e2", work_key="w"), collection="church-fathers",
                  title="The Epistles of Cyprian.", author="Cyprian.",
                  works=[Work(work_key="w", ordinal=1, title="To Cyprian", author="Firmilian of Caesarea")])
    assert content.letter_senders("church-fathers", [worked]) == {}
    # Leo's collection (5.6a): a title line with words before the sender's name, and one
    # naming the senders together, whose greeting names them.
    leo = [_letter("XXII", "The first from Flavian, Bp. of Constantinople to Pope Leo.",
                   "To the most holy father Leo, Flavian", "f1",
                   passage_author="Flavian of Constantinople"),
           _letter("LXVIII", "From Three Gallic Bishops to St. Leo.",
                   "Ceretius, Salonius and Veranus to Leo,", "g1",
                   passage_author="Ceretius, Salonius and Veranus")]
    leo_letters = _doc(*leo, collection="church-fathers", title="Letters", author="Leo the Great")
    assert content.letter_senders("church-fathers", [leo_letters]) == {}
    leo[1].passage_author = None                # credited to Leo, as it would be by default
    assert content.letter_senders("church-fathers", [leo_letters]) == {
        "attribution.letter_sender:church-fathers/doc-1": ["g1"]}


def test_narrative_of_author_death():
    def row(title, author, basis=None, works=()):
        return {"collection": "church-fathers", "document_id": "doc-1", "title": title,
                "author": author, "attribution": {"credited_as": None, "basis": basis},
                "works": list(works)}
    assert content.narrative_of_author_death([row("The Martyrdom of Polycarp", "Polycarp")]) == {
        "attribution.narrative_of_author_death:church-fathers/doc-1": ["The Martyrdom of Polycarp"]}
    for good in (row("The Martyrdom of Polycarp", "Church of Smyrna"),
                 row("The Martyrdom of Ignatius", "Ignatius", basis="An account by his companions."),
                 row("Epistle to the Philippians", "Polycarp")):
        assert content.narrative_of_author_death([good]) == {}
    nested = row("Acts", "Anonymous", works=[{"title": "The Passion of Perpetua", "author": "Perpetua"}])
    assert content.narrative_of_author_death([nested])


def test_unique_reference():
    twice = _doc(_p(anchor="a", reference="T, Chapter I"), _p(anchor="b", reference="T, Chapter I"),
                 _p(anchor="c", reference="T, Chapter II"))
    assert content.unique_references("medieval", [twice]) == {
        "labels.unique_reference:medieval/doc-1": ["T, Chapter I"]}
    pieces = _doc(_p(anchor="a", reference="T, Chapter I (part 1 of 2)"),
                  _p(anchor="a/from-p3", reference="T, Chapter I (part 2 of 2)"))
    assert content.unique_references("medieval", [pieces]) == {}
    # The Summa and the Catechism join once 1.7 and 1.6 cite their pieces.
    assert not any(k.startswith("labels.unique_reference")
                   for k in content.run("catechism", [twice], works=[]))


def test_reference_author_consistent():
    bad = _doc(_p(reference="Justin Martyr — Hortatory Address, Chapter I", passage_author="Pseudo-Justin"),
               collection="church-fathers", author="Justin Martyr")
    assert content.reference_author_consistent("church-fathers", [bad]) == {
        "labels.reference_author_consistent:church-fathers/doc-1": ["a"]}
    good = _doc(_p(reference="Justin Martyr. — Hortatory Address, Chapter I"),
                _p(reference="Hortatory Address, Chapter II", anchor="b"),
                collection="church-fathers", author="Justin Martyr")
    assert content.reference_author_consistent("church-fathers", [good]) == {}


def test_roman_case():
    bad = _doc(_p(chapter_label="Iii."), _p(anchor="b", chapter_label="Book XII · Chapter Xi"))
    assert content.roman_case("church-fathers", [bad]) == {
        "labels.roman_case:church-fathers/doc-1": ["a", "b"]}
    good = _doc(_p(chapter_label="III."), _p(anchor="b", chapter_label="Civil Ill Mix Vivid"))
    assert content.roman_case("church-fathers", [good]) == {}


def test_unique_titles():
    docs = [_doc(_p(), title="Fragments."), _doc(_p(), doc_id="doc-2", title="fragments"),
            _doc(_p(), doc_id="doc-3", title="Smyrnæans")]
    assert content.unique_titles("church-fathers", docs) == {
        "registry.unique_title_per_collection:church-fathers": ["fragments"]}
    assert content.unique_titles("church-fathers", docs[1:]) == {}


def test_canon_ligature_corruption():
    bad = _doc(_p("a diVerent and suYcient cause", metadata={"canon": 253}),
               _p("The Vatican and York agree.", anchor="b", metadata={"canon": 254}),
               collection="canon-law")
    assert content.canon_ligature_corruption([bad]) == {
        "text.canon_law.ligature_corruption:canon-law": ["253"]}


# --------------------------------------------------------------------------- unit coverage

def test_catechism_paragraph_words():
    units = [SourceUnit("ccc-us.json", "10", PROSE, "body"),
             SourceUnit("ccc-us.json", "11", "One two three four five.", "body"),
             SourceUnit("ccc-us.json", None, "A HEADING", "heading")]
    good = _doc(_p(PROSE, reference="CCC §10–11 (part)"),
                _p("One two three four five.", anchor="b", reference="CCC §11 (part)"),
                collection="catechism")
    assert unit_coverage.catechism_paragraph_words([good], units) == {}
    lossy = _doc(_p(PROSE.replace(" at all", ""), reference="CCC §10"),
                 _p("One two three four five.", anchor="b", reference="CCC §11"),
                 collection="catechism")
    out = unit_coverage.catechism_paragraph_words([lossy], units)
    assert list(out) == ["coverage.catechism.paragraph_words:10"]
    assert report.check_scope("coverage.catechism.paragraph_words:10") == "catechism"


USFM = (r"\id PSA" "\n" r"\c 3" "\n" r"\d A Psalm by David, when he fled from his son." "\n"
        r"\q1" "\n" r"\v 1 LORD, how my adversaries have increased!" "\n"
        r"\v 2 Many are those who rise up against me." "\n")


def test_usfm_psalm_title_is_body_and_not_a_verse(tmp_path, monkeypatch):
    path = tmp_path / "20-PSA.usfm"
    path.write_text(USFM)
    units = usfm_units(str(path))
    assert ("PSA/3/d", "body") in [(u.unit_id, u.region) for u in units]
    # The verse check reads only numbered units: the title neither raises nor is "missing"
    # (no documents are placed here, so both verses are).
    monkeypatch.setattr(seq, "documents_by_file", lambda c, docs, files, *a: {f: [] for f in files})
    result = seq.bible_verses([], units)
    assert result.missing == ["PSA/3/1", "PSA/3/2"] and not result.out_of_range


def test_bible_superscriptions(tmp_path):
    path = tmp_path / "20-PSA.usfm"
    path.write_text(USFM)
    units = usfm_units(str(path))
    verses = "LORD, how my adversaries have increased! Many are those who rise up against me."
    missing = _doc(_p(verses, anchor="psalms/3/1", chapter_key="psalms/3"), title="Psalms",
                   collection="bible")
    assert unit_coverage.bible_superscriptions([missing], units) == {
        "coverage.bible.superscriptions": ["PSA/3"]}
    held = _doc(_p("A Psalm by David, when he fled from his son. " + verses, anchor="psalms/3/1",
                   chapter_key="psalms/3"), title="Psalms", collection="bible")
    assert unit_coverage.bible_superscriptions([held], units) == {}



PSALM_119 = (r"\id PSA" "\n" r"\c 119" "\n" r"\d ALEPH" "\n" r"\q1" "\n"
             r"\v 1 Blessed are those whose ways are blameless." "\n"
             r"\d BETH" "\n" r"\q1" "\n" r"\v 2 How can a young man keep his way pure?" "\n")


def test_bible_superscriptions_later_letters_head_their_verse(tmp_path):
    # Psalm 119's later letters (1.4a) need not sit in the first passage, but each must
    # open the verse it heads in one of the psalm's passages.
    path = tmp_path / "20-PSA.usfm"
    path.write_text(PSALM_119)
    units = usfm_units(str(path))

    def psalm(*texts):
        return _doc(*[_p(t, anchor=f"psalms/119/{i}", chapter_key="psalms/119")
                      for i, t in enumerate(texts, 1)], title="Psalms", collection="bible")

    held = psalm("ALEPH Blessed are those whose ways are blameless.",
                 "{{v:2}} BETH How can a young man keep his way pure?")
    assert unit_coverage.bible_superscriptions([held], units) == {}
    # BETH somewhere else in the psalm (or missing) does not count.
    elsewhere = psalm("ALEPH Blessed are those whose ways are blameless. BETH",
                      "{{v:2}} How can a young man keep his way pure?")
    assert unit_coverage.bible_superscriptions([elsewhere], units) == {
        "coverage.bible.superscriptions": ["PSA/119"]}


def test_bible_verses_skip_a_prologue(monkeypatch):
    units = [SourceUnit("46-SIR.usfm", "SIR/1/1", "All wisdom comes from the Lord.", "body")]
    doc = _doc(_p("Whereas many things.", anchor="sirach/prologue", reference="Sirach, Prologue"),
               _p("All wisdom comes from the Lord.", anchor="sirach/1/1", reference="Sirach 1"),
               title="Sirach", collection="bible")
    monkeypatch.setattr(seq, "documents_by_file", lambda c, docs, files, *a: {f: [doc] for f in files})
    result = seq.bible_verses([doc], units)
    assert not result.missing and not result.out_of_range


def test_ccc_1471_definition_by_hash(monkeypatch):
    sentence = "A defining sentence of this paragraph is written here for the test."
    key = match_key(split_sentences(sentence)[0])
    monkeypatch.setattr(unit_coverage, "CCC_1471_SHA256", hashlib.sha256(key.encode()).hexdigest())
    monkeypatch.setattr(unit_coverage, "CCC_1471_LENGTH", len(key))
    units = [SourceUnit("ccc-us.json", "1471", f"{sentence} Another sentence follows it.", "body")]
    assert unit_coverage.ccc_1471_definition([_doc(_p(sentence), collection="catechism")], units) == 1
    assert unit_coverage.ccc_1471_definition([_doc(_p(PROSE), collection="catechism")], units) == 0
    # A source that no longer holds the recorded sentence reads as absent, not present.
    assert unit_coverage.ccc_1471_definition([_doc(_p(sentence))], units[:0]) == 0


def test_sirach_prologue(tmp_path):
    folder = tmp_path / "bible" / "eng-web-c_usfm"
    folder.mkdir(parents=True)
    prologue = ("WHEREAS many and great things have been delivered to us by the law. "
                "You are entreated therefore to read with favor and attention.")
    (folder / "46-SIReng-web-c.usfm").write_text(
        "\\id SIR\n\\ip This book is recognized as Deuterocanonical Scripture by many.\n"
        f"\\is1 The Prologue of the Wisdom of Jesus the Son of Sirach.\n\\ip {prologue}\n"
        "\\c 1\n\\v 1 All wisdom comes from the Lord.\n")
    without = _doc(_p("All wisdom comes from the Lord."), title="Sirach", collection="bible")
    with_it = _doc(_p(prologue), _p("All wisdom comes from the Lord.", anchor="b"),
                   title="Sirach", collection="bible")
    assert unit_coverage.sirach_prologue([without], str(tmp_path)) == 0
    assert unit_coverage.sirach_prologue([with_it], str(tmp_path)) == 100


# --------------------------------------------------------------------------- outline

def _write_snapshot(tmp_path, chapters, chunk_count=3):
    (tmp_path / "documents.jsonl").write_text(json.dumps({"id": "doc-1", "chunk_count": chunk_count}) + "\n")
    if chapters is not None:
        (tmp_path / "document_chapters.jsonl").write_text(
            "".join(json.dumps({"document_id": "doc-1", "ordinal": o, "chapter_key": k,
                                "chapter_label": l, "chunk_count": chunk_count}) + "\n"
                    for o, k, l in chapters))
    return str(tmp_path)


def _outline_doc():
    return _doc(_p(anchor="a", chapter_key="k1", chapter_label="One"),
                _p(anchor="b", chapter_key="k2", chapter_label="Two"),
                _p(anchor="c", chapter_key="k2", chapter_label="Two"))


def test_outline_matches(tmp_path):
    snapshot = _write_snapshot(tmp_path, [(1, "k1", "One"), (2, "k2", "Two")])
    assert outline.outline_failures(snapshot, {"encyclicals": [_outline_doc()]}) == []


def test_outline_mismatch_is_a_release_failure(tmp_path):
    snapshot = _write_snapshot(tmp_path, [(1, "k2", "Two"), (2, "k1", "Uno")])
    [f] = outline.outline_failures(snapshot, {"encyclicals": [_outline_doc()]})
    assert f.check_id == "release.outline_matches:encyclicals/doc-1"
    assert "k1: ordinal 2, expected 1" in f.detail and "k2: ordinal 1, expected 2" in f.detail
    assert report.check_scope(f.check_id) == "encyclicals"


def test_outline_label_and_missing_rows(tmp_path):
    snapshot = _write_snapshot(tmp_path, [(1, "k1", "Uno")])
    [f] = outline.outline_failures(snapshot, {"encyclicals": [_outline_doc()]})
    assert "k1: label differs" in f.detail and "k2: not stored" in f.detail


def test_outline_skips_a_document_with_no_current_outline_and_a_snapshot_without_the_file(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    stale = _write_snapshot(tmp_path / "a", [(1, "k2", "Two")], chunk_count=None)
    assert outline.outline_failures(stale, {"encyclicals": [_outline_doc()]}) == []
    assert outline.outline_failures(_write_snapshot(tmp_path / "b", None),
                                    {"encyclicals": [_outline_doc()]}) is None


# --------------------------------------------------------------------------- report

@pytest.mark.parametrize("check_id,collection", [
    ("structure.chapter_contiguous:canon-law", "canon-law"),
    ("structure.chapter_sequence:councils/doc-1", "councils"),
    ("roles.summa.objection-after-replies:summa", "summa"),
    ("editorial.argument_lines:church-fathers/doc-1", "church-fathers"),
    ("attribution.letter_sender:church-fathers/doc-1", "church-fathers"),
    ("labels.roman_case:medieval/doc-1", "medieval"),
    ("registry.unique_title_per_collection:church-fathers", "church-fathers"),
    ("text.canon_law.ligature_corruption:canon-law", "canon-law"),
    ("health.R11_papal_editorial:encyclicals/doc-1", "encyclicals"),
    ("coverage.bible.superscriptions", "bible"),
    ("sentinel.ccc_1471_definition", "catechism"),
    ("sentinel.sirach_prologue", "bible"),
])
def test_check_scope_covers_the_new_namespaces(check_id, collection):
    assert report.check_scope(check_id) == collection
    assert check_id.startswith(report.REPORT_PREFIXES)


def test_unit_coverage_ids_are_not_file_coverage():
    assert report.is_file_coverage("coverage.bible.eng-web-c_usfm/20-PSAeng-web-c.usfm")
    assert not report.is_file_coverage("coverage.bible.superscriptions")
    assert not report.is_file_coverage("coverage.catechism.paragraph_words:1471")


def test_failing_checks_include_review_failures():
    result = report.RunResult(["summa"])
    result.review = {"structure.summa.one-disputation-per-article:summa": ["SS_Q64_A7"]}
    assert report.failing_checks(result) == result.review
    known = {"structure.summa.one-disputation-per-article:summa": {
        "fixed_by": "1.7", "description": "d", "units": ["SS_Q64_A7"]}}
    result.review["structure.summa.one-disputation-per-article:summa"].append("SS_Q66_A5")
    assert report.grown_defects(report.failing_checks(result), known) == {
        "structure.summa.one-disputation-per-article:summa": ["SS_Q66_A5"]}
