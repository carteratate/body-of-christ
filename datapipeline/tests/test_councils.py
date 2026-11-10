import os, sys, re
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup
from ingest.councils import build_vatican2, build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "councils")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))

# --- Vatican II (1.1) ----------------------------------------------------------------

def _v2(title, html, document_type="constitution"):
    entry = {"council": "Second Vatican Council", "document": title,
             "document_type": document_type, "year": 1965, "group": "vatican-ii",
             "file": "x.html", "url": "http://example"}
    return build_vatican2(entry, BeautifulSoup(html, "lxml"))


VAT2_HTML = """<html><body>
<p align="right">[ <a href="/ar">AR</a> - EN - <a href="/fr">FR</a> ]</p>
<p>DOGMATIC CONSTITUTION ON DIVINE REVELATION <b>DEI VERBUM</b></p>
<center><b>CHAPTER I</b><p><b>REVELATION ITSELF</b></p></center>
<p>1. In His goodness and wisdom God chose to reveal Himself and to make known the mystery of His will.(1)</p>
<p>As a sacred synod has affirmed, God can be known with certainty from created reality. (2)</p>
<p>2. By this revelation the invisible God out of the abundance of His love speaks to men as friends.</p>
<hr/><p><b>NOTES</b></p>
<p>1. Cf. Eph. 1:9.</p>
<p>2. Cf. Rom. 1:20, which the synod quotes at length in its second section here.</p>
<p>3. Ibid.</p>
</body></html>"""


def test_vatican2_numbered_paragraphs_under_chapter():
    d = _v2("Dei Verbum", VAT2_HTML)
    assert d.title == "Dei Verbum" and d.author == "Second Vatican Council"
    assert d.metadata["council"] == "Second Vatican Council"
    assert [p.unit_label for p in d.passages] == ["§1", "§2"]
    assert [p.anchor for p in d.passages] == ["dei-verbum/1", "dei-verbum/2"]
    assert {p.chapter_label for p in d.passages} == {"Chapter I: Revelation Itself"}


def test_vatican2_continuations_join_their_section():
    first = _v2("Dei Verbum", VAT2_HTML).passages[0]
    assert first.content == ("In His goodness and wisdom God chose to reveal Himself and to make "
                             "known the mystery of His will.\n\nAs a sacred synod has affirmed, "
                             "God can be known with certainty from created reality.")


def test_vatican2_stops_at_notes_heading():
    for heading in ("NOTES", "ENDNOTES", "Footnotes"):
        d = _v2("Dei Verbum", VAT2_HTML.replace("<b>NOTES</b>", heading))
        assert len(d.passages) == 2
        text = " ".join(p.content for p in d.passages)
        assert "Cf." not in text and "Ibid" not in text and "(1)" not in text


def test_vatican2_notes_numbering_restart_is_not_a_section():
    html = """<html><body>
<p>1. The first section of the decree, which is long enough to be a section of its own.</p>
<p>2. The second section, which sets out a list of norms that follow in order below.</p>
<p>1. A norm numbered inside the second section, which is not a section of the decree.</p>
<p>2. Another such norm; the running count expects 3, so this is still the second section.</p>
<p>3. The third section of the decree, which closes it before the notes begin below.</p>
<p>ENDNOTES</p><p>Chapter I</p>
<p>1. Cf. Matt. 28:19.</p><p>2. Cf. Mark 16:15.</p><p>3. Cf. Luke 24:47.</p><p>4. Cf. John 20:21.</p>
</body></html>"""
    d = _v2("Ad Gentes", html, "decree")
    assert [p.unit_label for p in d.passages] == ["§1", "§2", "§3"]
    assert "A norm numbered inside" in d.passages[1].content
    assert "Another such norm" in d.passages[1].content


def test_vatican2_preface_before_section_one():
    plain = """<html><body>
<p>DECREE ON PRIESTLY TRAINING OPTATAM TOTIUS</p>
<p>Animated by the spirit of Christ, this sacred synod is fully aware that renewal depends on priests.</p>
<center><b>I.</b><p><b>THE PROGRAM OF PRIESTLY TRAINING</b></p></center>
<p>1. Since only general laws can be made where there exists a wide variety of nations and regions.</p>
</body></html>"""
    d = _v2("Optatam Totius", plain, "decree")
    assert [(p.anchor, p.reference, p.chapter_label) for p in d.passages] == [
        ("optatam-totius/preface", "Optatam Totius, Preface", "Preface"),
        ("optatam-totius/1", "Optatam Totius, §1", "I. The Program of Priestly Training")]
    headed = """<html><body>
<center><b>INTRODUCTION</b></center>
<p>The Sacred Ecumenical Council has considered with care how extremely important education is.</p>
<p><b><i>1. The Meaning of the Universal Right to an Education</i></b></p>
<p>All men of every race, condition and age have an inalienable right to an education.</p>
<center><b>CONCLUSION</b></center>
<p>The Fathers of this holy synod have pursued the work begun, and close with an exhortation.</p>
</body></html>"""
    d = _v2("Gravissimum Educationis", headed, "declaration")
    assert [(p.anchor, p.unit_label, p.chapter_label) for p in d.passages] == [
        ("gravissimum-educationis/preface", "Introduction", "Introduction"),
        ("gravissimum-educationis/1", "§1", "1. The Meaning of the Universal Right to an Education"),
        ("gravissimum-educationis/conclusion", "Conclusion", "Conclusion")]
    assert d.passages[1].content.startswith(
        "The Meaning of the Universal Right to an Education\n\nAll men of every race")


LG_HTML = """<html><body>
<center><b>CHAPTER I</b><p><b>THE MYSTERY OF THE CHURCH</b></p></center>
<p>1. Christ is the Light of nations. Because this is so, this Sacred Synod eagerly desires (1) it.</p>
<p>2. The eternal Father, by a free and hidden plan of His own wisdom and goodness, created the world.</p>
<p>Each and all these items which are set forth in this dogmatic Constitution have met with approval.</p>
<p><i>Given in Rome at St. Peter's on November 21, 1964.</i></p>
<center><b>APPENDIX <br/> From the Acts of the Council*</b></center>
<center><b><i>'NOTIFICATIONES' GIVEN BY THE SECRETARY GENERAL</i></b></center>
<p>A question has arisen regarding the precise theological note which should be attached to it.</p>
<p><b><i>Preliminary Note of Explanation </i></b></p>
<p>The Commission has decided to preface the assessment of the Modi with general observations.</p>
<p>1. "College" is not understood in a strictly juridical sense, that is as a group of equals.</p>
<p>2. A person becomes a member of the College by virtue of Episcopal consecration [munus].</p>
<p>N.B. Without hierarchical communion the ontologico-sacramental function cannot be exercised.</p>
<center><b>+ PERICLE FELICI </b><br/><i>Titular Archbishop of Samosata</i></center>
<p><b>NOTES</b></p><p>1 Cf. Mk. 16:15.</p>
</body></html>"""


def test_vatican2_nota_praevia_has_own_anchors():
    d = _v2("Lumen Gentium", LG_HTML)
    got = [(p.anchor, p.reference, p.chapter_label) for p in d.passages]
    assert got == [
        ("lumen-gentium/1", "Lumen Gentium, §1", "Chapter I: The Mystery of the Church"),
        ("lumen-gentium/2", "Lumen Gentium, §2", "Chapter I: The Mystery of the Church"),
        ("lumen-gentium/promulgation", "Lumen Gentium, Promulgation", "Promulgation"),
        ("lumen-gentium/notificationes",
         "Lumen Gentium, Notificationes of the Secretary General",
         "Notificationes of the Secretary General"),
        ("lumen-gentium/nota-praevia/1", "Lumen Gentium, Preliminary Note of Explanation, 1",
         "Preliminary Note of Explanation"),
        ("lumen-gentium/nota-praevia/2", "Lumen Gentium, Preliminary Note of Explanation, 2",
         "Preliminary Note of Explanation")]
    by = {p.anchor: p.content for p in d.passages}
    assert by["lumen-gentium/promulgation"].endswith("Given in Rome at St. Peter's on November 21, 1964.")
    assert by["lumen-gentium/nota-praevia/1"].startswith("The Commission has decided")
    # The page's own words stay, brackets included; the signature closes the Note.
    assert "[munus]" in by["lumen-gentium/nota-praevia/2"]
    assert by["lumen-gentium/nota-praevia/2"].endswith("+ PERICLE FELICI Titular Archbishop of Samosata")
    assert "(1)" not in by["lumen-gentium/1"]


def _numbered(numbers, extra):
    body = "\n".join(f"<p>{n}. Section {n} of the document, long enough to stand as a section here.</p>"
                     for n in numbers)
    return f"<html><body>{body}{extra}</body></html>"


def test_vatican2_section_number_fix_applied():
    html = _numbered(range(1, 87), "<p>81. In order that the divine office may be prayed better.</p>"
                     "<p>88. The next section, which follows the corrected one in its proper place.</p>")
    d = _v2("Sacrosanctum Concilium", html)
    by = {p.unit_label: p for p in d.passages}
    assert by["§87"].anchor == "sacrosanctum-concilium/87"
    assert by["§87"].content.startswith("In order that the divine office")
    assert [p.unit_label for p in d.passages] == [f"§{n}" for n in range(1, 89)]
    html = _numbered(range(1, 21), "<p>But since it is necessary for the students to learn the art.</p>"
                     "<p>21. Since priestly training must be continued after the seminary.</p>")
    d = _v2("Optatam Totius", html, "decree")
    assert [(p.anchor, p.unit_label) for p in d.passages[-2:]] == [
        ("optatam-totius/para-21", "§21"), ("optatam-totius/22", "§22")]


def test_vatican2_subheadings_open_the_next_section_and_bare_chapters_take_their_title():
    html = """<html><body>
<center><b>CHAPTER</b><p><b>VI SACRED MUSIC</b></p></center>
<p>1. The musical tradition of the universal Church is a treasure of inestimable value, greater.</p>
<p><b>A) General norms</b></p>
<p>2. Regulation of the sacred liturgy depends solely on the authority of the Church, that is.</p>
<p><b>PART II</b></p><p><b>SOME PROBLEMS OF SPECIAL URGENCY</b></p>
<center><b>CHAPTER I</b><p><b>FOSTERING THE NOBILITY OF MARRIAGE</b></p></center>
<p>3. The well-being of the individual person and of human and Christian society is intimately linked.</p>
</body></html>"""
    d = _v2("Gaudium et Spes", html)
    assert [p.chapter_label for p in d.passages] == [
        "Chapter VI: Sacred Music", "Chapter VI: Sacred Music",
        "Part II, Chapter I: Fostering the Nobility of Marriage"]
    assert d.passages[1].content.startswith("A) General norms\n\nRegulation of the sacred liturgy")
    assert d.passages[0].content.endswith("greater.")


VAT2_FLAT_HTML = """<html><body>
""" + "\n".join(
    f"<p>{i}. This is numbered paragraph {i} of a declaration with no chapter headings at all here.</p>"
    for i in range(1, 26)
) + """
</body></html>"""


def test_vatican2_headerless_falls_back_to_paragraph_buckets():
    d = _v2("Dignitatis Humanae", VAT2_FLAT_HTML, "declaration")
    assert len(d.passages) == 25
    labels = {p.chapter_label for p in d.passages}
    # 25 paragraphs in buckets of 20 → "Paragraphs 1–20" and "Paragraphs 21–40"
    assert labels == {"Paragraphs 1–20", "Paragraphs 21–40"}
    assert all(p.anchor and p.chapter_key for p in d.passages)


# The sections of each document, as the Latin numbers them (Optatam Totius 22: Carter,
# 10 Nov 2026).
V2_SECTIONS = {"Dei Verbum": 26, "Lumen Gentium": 69, "Sacrosanctum Concilium": 130,
               "Gaudium et Spes": 93, "Ad Gentes": 42, "Presbyterorum Ordinis": 22,
               "Apostolicam Actuositatem": 33, "Optatam Totius": 22, "Perfectae Caritatis": 25,
               "Christus Dominus": 44, "Unitatis Redintegratio": 24,
               "Orientalium Ecclesiarum": 30, "Inter Mirifica": 24,
               "Gravissimum Educationis": 12, "Nostra Aetate": 5, "Dignitatis Humanae": 15}


def _vatican2():
    return [d for d in build_documents() if d.title in V2_SECTIONS]


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_vatican2_every_section_once():
    for d in _vatican2():
        sections = [p.unit_label for p in d.passages
                    if p.unit_label.startswith("§") and "/from-" not in p.anchor]
        assert sections == [f"§{n}" for n in range(1, V2_SECTIONS[d.title] + 1)], d.title
        assert d.author == "Second Vatican Council"


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_vatican2_keeps_the_page_body():
    from checks.coverage import coverage
    from checks.source_text import file_units
    docs = _vatican2()
    units = [u for d in docs
             for u in file_units("councils", d.metadata["source_key"].split("/", 1)[1] + ".html")]
    result = coverage("councils", docs, units)
    for d in docs:
        assert result.documents[d.id].pct >= 99, (d.title, result.documents[d.id].pct)
    assert sum(r.body_chars for r in result.documents.values()) > 900_000


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_vatican2_no_passage_is_a_note_or_holds_a_caller():
    from checks.structure import chapter_sequence
    from health import check_documents
    docs = _vatican2()
    for d in docs:
        for p in d.passages:
            assert not p.content.startswith(("Cf.", "cf.", "See ", "Ibid")), p.anchor
    assert not [v for v in check_documents("councils", docs) if v.rule == "R12_note_caller"]
    assert chapter_sequence("councils", docs) == {}


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_nostra_aetate_4_keeps_the_passage_on_the_passion():
    d, = [d for d in _vatican2() if d.title == "Nostra Aetate"]
    four = " ".join(p.content for p in d.passages if p.unit_label == "§4")
    assert "what happened in His passion cannot be charged against all the Jews" in four
    assert len(four) > 3500


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_vatican2_chapters_carry_number_and_title():
    by = {d.title: list(dict.fromkeys(p.chapter_label for p in d.passages)) for d in _vatican2()}
    lg = [x for x in by["Lumen Gentium"] if x.startswith("Chapter ")]
    assert [x.split(":")[0] for x in lg] == [f"Chapter {n}" for n in
                                            "I II III IV V VI VII VIII".split()]
    assert lg[6] == ("Chapter VII: The Eschatological Nature of the Pilgrim Church and Its "
                     "Union with the Church in Heaven")
    assert by["Lumen Gentium"][-3:] == ["Promulgation", "Notificationes of the Secretary General",
                                        "Preliminary Note of Explanation"]
    sc = [x for x in by["Sacrosanctum Concilium"] if x.startswith("Chapter ")]
    assert [x.split(":")[0] for x in sc] == [f"Chapter {n}" for n in "I II III IV V VI VII".split()]
    assert "Chapter VI: Sacred Music" in sc
    assert by["Sacrosanctum Concilium"][-1] == "Appendix: Declaration on the Revision of the Calendar"
    gs = by["Gaudium et Spes"]
    assert len(gs) == len(set(gs)) and "Part II, Chapter I: Fostering the Nobility of Marriage and the Family" in gs
    lg_by = {p.anchor: p for d in _vatican2() if d.title == "Lumen Gentium" for p in d.passages}
    assert [a for a in lg_by if "nota-praevia" in a] == [
        f"lumen-gentium/nota-praevia/{n}" for n in range(1, 5)]
    for n in (48, 49, 50, 51):    # eschatology and purgatory (C-20)
        assert lg_by[f"lumen-gentium/{n}"].chapter_label.startswith("Chapter VII:")


def test_vatican2_registry_keeps_each_unit_on_its_id():
    reg = work_registry.current()
    rows = {(r["document_id"], r["live_anchor"]): r for r in reg.passages}
    sc, ot, lg, ge = ("29bf3975-5f39-5550-a949-6767cb666695", "b58729e8-fa6e-5b91-9d66-b0734050a471",
                      "c1b748c6-a250-5ca1-a087-4f6be5e75bbb", "6f6474ba-c632-5bdb-a550-b8d5c61797a9")
    # The same unit under its corrected anchor keeps its ID.
    assert rows[(sc, "sacrosanctum-concilium/81-2")]["anchor"] == "sacrosanctum-concilium/87"
    assert rows[(ot, "optatam-totius/21")]["anchor"] == "optatam-totius/22"
    for n in range(1, 5):
        row = rows[(lg, f"lumen-gentium/{n}-2")]
        assert (row["anchor"], row["status"]) == (f"lumen-gentium/nota-praevia/{n}", "active")
    # A footnote card retires; a live footnote's anchor is never a section's.
    removed = {e["anchor"]: e for e in work_registry.open_removals(reg) if e["anchor"]}
    for anchor in ("dei-verbum/5-2", "nostra-aetate/11", "gravissimum-educationis/2"):
        assert removed[anchor]["reason"] == "note-split-off"
        assert removed[anchor]["tombstone"] == ("This card was a footnote to the Council's "
                                                "text, not the text itself.")
    assert rows[(ge, "gravissimum-educationis/1")]["status"] == "active"
    assert not [r for r in reg.passages if r["document_id"] == ge and r["status"] == "active"
                and r["anchor"] in {f"gravissimum-educationis/{n}" for n in (2, 3, 4, 5, 6, 8, 9, 10, 11)}]
    # A sub-paragraph card set apart from its section follows its text there.
    redirects = {r["old_anchor"]: r for r in reg.redirects if not r.get("closed_by")}
    assert redirects["sacrosanctum-concilium/2-2"]["new_anchor"] == "sacrosanctum-concilium/22"
    assert redirects["sacrosanctum-concilium/2-2"]["kind"] == "merged"


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
                "Fifth Lateran Council": 7, "Council of Constance": 7,
                "Council of Basel-Ferrara-Florence": 15}
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
    if council == "Council of Basel-Ferrara-Florence":    # sessions 20 and 21
        series = (4, 11)
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


# Quotations the page opens and never closes: "from things sacrificed to idols, … from things
# strangled" (Cantate Domino, Deferrari p. 229).
PRINTED_UNCLOSED_QUOTE = {"florence-session-11/cantate-domino-07"}


@pytest.mark.parametrize("work", [*schroeder.WORKS.values(),
                                  *(w for w, _ in deferrari.WORKS.values())])
def test_frozen_text_marks_balance_and_sentences_start_clean(work):
    # What a word-level comparison misses: a lost bracket or quotation mark, or a stop
    # read as a comma or a comma as a stop. A unit that `continues` the one before is
    # checked with it: a quotation can run across the cut (Exultate Deo, p. 222).
    units: list[dict] = []
    for unit in read_text(work)["passages"]:
        if unit.get("continues") and units:
            units[-1] = {"id": units[-1]["id"], "text": f"{units[-1]['text']} {unit['text']}"}
        else:
            units.append(unit)
    for unit in units:
        text = unit["text"]
        assert text.count("(") == text.count(")"), unit["id"]
        assert _quotations_balance(text), unit["id"]
        if unit["id"] not in PRINTED_UNCLOSED_QUOTE:
            assert text.count('"') % 2 == 0, unit["id"]      # Deferrari's are straight
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
        # Denzinger's numbers; a date the sentence gives is the text's ("July 6, 1415").
        undated = re.sub(r"[A-Z][a-z]+ \d{1,2}, \d{4}\b", "", text)
        assert not re.search(r"\b\d{3,4}[a-z]?\b", undated), unit["id"]
        assert not re.search(r"\[(?:see|cf\.)|\[[^\]]*\d+\s?:\s?\d+", text), unit["id"]
        assert not re.search(r"Anastasius:|\bCan\.\s*\d", text), unit["id"]


@pytest.mark.parametrize("council", ["Fourth Council of Constantinople", "Fifth Lateran Council",
                                     "Council of Constance", "Council of Basel-Ferrara-Florence"])
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
    for council in ("Fourth Council of Constantinople", "Fifth Lateran Council",
                    "Council of Constance", "Council of Basel-Ferrara-Florence"):
        assert rows[council]["document_id"] and rows[council]["planned_for"] is None
        also, = rows[council]["also_from"]
        assert also["source_path"] == "councils/sources-of-catholic-dogma/"
        assert also["status"] == "pd-us-non-renewal" and also["translator"] == "Roy J. Deferrari"


# --- Constance and Basel-Ferrara-Florence, with Deferrari's texts (1.2e-5) ------------------

CONSTANCE = {**SCHROEDER_ENTRY, "council": "Council of Constance", "year": 1418}
BASEL_FLORENCE = {**SCHROEDER_ENTRY, "council": "Council of Basel-Ferrara-Florence", "year": 1445}
ARTICLES_NOTE = ("Articles the council condemned, not its teaching. Its sentence is not available on "
                 "TheoCorpus at present. Translated by R. J. Deferrari (1957).")


def test_constance_is_built_by_session_with_deferraris_texts_before_session_43():
    doc = _schroeder(CONSTANCE)
    slug = "council-of-constance"
    assert _units(doc) == [f"{slug}/{u}" for u in (
        "session-8/wyclif-articles", "session-13/communion-under-one-kind",
        "session-15/hus-articles", "session-15/tyrannicide",
        *(f"session-43/decree/{n}" for n in range(1, 8)))]
    labels = {p.anchor.split("/from-")[0]: (p.chapter_key, p.chapter_label, p.unit_label) for p in doc.passages}
    assert labels[f"{slug}/session-8/wyclif-articles"] == (f"{slug}/session-8", "Session 8", "Articles of Wyclif")
    assert labels[f"{slug}/session-43/decree/3"] == (f"{slug}/session-43", "Session 43", "Decree 3")
    # One article to a paragraph, packed into passages; the lists keep their own numbers.
    wyclif = "\n\n".join(p.content for p in doc.passages if "/wyclif-articles" in p.anchor).split("\n\n")
    hus = "\n\n".join(p.content for p in doc.passages if "/hus-articles" in p.anchor).split("\n\n")
    assert [int(a.split(".")[0]) for a in wyclif] == list(range(1, 46))
    assert [int(a.split(".")[0]) for a in hus] == list(range(1, 31))
    assert doc.translation == f"{schroeder.TRANSLATION}; {deferrari.TRANSLATION}"


def test_basel_ferrara_florence_names_the_place_of_each_session():
    doc = _schroeder(BASEL_FLORENCE)
    slug = "council-of-basel-ferrara-florence"
    assert _units(doc) == [f"{slug}/{u}" for u in (
        *(f"basel-session-20/decree/{n}" for n in range(1, 5)),
        *(f"basel-session-21/decree/{n}" for n in range(5, 16)),
        "florence-session-6/laetentur-caeli", "florence-session-8/exultate-deo",
        "florence-session-11/cantate-domino")]
    first = doc.passages[0]
    assert (first.chapter_key, first.chapter_label, first.unit_label) == (
        f"{slug}/basel-session-20", "Basel, Session 20", "Decree 1")
    cantate = next(p for p in doc.passages if p.anchor.endswith("/cantate-domino"))
    assert (cantate.chapter_label, cantate.reference.split(" (")[0]) == (
        "Florence, Session 11", "Council of Basel-Ferrara-Florence, Florence, Session 11, Cantate Domino")
    # The corrigenda of n. 691 and n. 703 are applied.
    text = " ".join(p.content for p in doc.passages)
    assert "And since all that the Father has, the Father himself, in begetting" in text
    assert "one eternity and all these things are one, where" in text
    assert "(The decrees for Greeks" not in text and "[The books of the canon" not in text


@pytest.mark.skipif(not _vendored, reason="needs the vendored manifest")
def test_constance_and_basel_ferrara_florence_carry_their_notes_on_every_piece():
    for council in ("Council of Constance", "Council of Basel-Ferrara-Florence"):
        for p in _built(council).passages:
            unit = p.anchor.split("/from-")[0]
            if unit.endswith(("/wyclif-articles", "/hus-articles")):
                expected = ARTICLES_NOTE
            elif p.metadata["scan_id"] == DEFERRARI_SCAN:
                expected = EXTRACT_NOTE
            elif unit.endswith("/session-43/decree/1"):
                expected = "Abridged in Schroeder (1937)."
            else:
                expected = None
            assert p.note == expected, p.anchor


def test_tanners_constance_and_basel_ferrara_florence_go_where_their_text_went():
    reg = work_registry.current()
    open_ = {r["old_anchor"]: r["new_anchor"] for r in reg.redirects if not r.get("closed_by")}
    con, bff = "council-of-constance", "council-of-basel-ferrara-florence"
    # Each of Wyclif's and Hus's articles to the passage holding the same article.
    assert open_[f"{con}/sec-10/1"] == f"{con}/session-8/wyclif-articles"
    assert open_[f"{con}/sec-10/45"].startswith(f"{con}/session-8/wyclif-articles")
    assert open_[f"{con}/sec-17/1-2"] == f"{con}/session-15/hus-articles"
    assert open_[f"{con}/sec-15/19"] == f"{con}/session-13/communion-under-one-kind"
    assert open_[f"{con}/sec-17/27-3"] == f"{con}/session-15/tyrannicide"
    assert open_[f"{con}/sec-46/44"] == f"{con}/session-43/decree/1"
    assert open_[f"{bff}/sec-0/29"] == f"{bff}/basel-session-20/decree/1"
    assert open_[f"{bff}/sec-0/64"] == f"{bff}/florence-session-6/laetentur-caeli"
    removed = {e["anchor"]: e for e in work_registry.open_removals(reg)}
    assert "(gap G7)" in removed[f"{con}/sec-46/47"]["detail"]
    assert removed[f"{con}/sec-17/1"]["reason"] == "translation-in-preparation"   # the 58 articles
    assert removed[f"{bff}/sec-0/1"]["reason"] == "rule-g-editorial"
    # Every live passage of the two councils has an outcome; none keeps its ID.
    rows = [r for r in reg.passages if r["document_id"] in (
        "bfcce97d-adf8-5e3c-8b8f-7e7887a6b205", "706adce0-8af2-5a30-877b-82e701601a53")]
    assert not [r["anchor"] for r in rows if r["status"] == "active" and "/sec-" in r["anchor"]]


# --- Vatican I from Schaff's Creeds of Christendom (1.2d) ----------------------------------

from ingest import councils_schaff as schaff  # noqa: E402
from ingest.scripture_notes import scripture_reference  # noqa: E402

VATICAN_I = {"council": "First Vatican Council", "year": 1870, "council_number": 20,
             "url": "https://www.papalencyclicals.net/councils/ecum20.htm"}
_LA = '<td style="width:50%;vertical-align:top{style}"><span lang="LA"><i>{text}</i></span></td>'
_EN = '<td style="width:50%;vertical-align:top{style}">{text}</td>'


def _row(latin, english, style=""):
    return f"<tr>{_LA.format(style=style, text=latin)}{_EN.format(style=style, text=english)}</tr>"


SCHAFF_XML = f"""<?xml version="1.0"?>
<ThML><ThML.body><div2 id="v.ii">
<div3 type="Section" title="The Orthodox Confession of the Eastern Church, A.D. 1643." id="v.ii.i">
<pb n="234" id="v.ii.i-Page_234" />
<p>[The Latin text from Acta et Decreta ... The English translation from Manning.]</p>
<table>
{_row("Constitutio Dogmatica de Fide Catholica", "Dogmatic Constitution on the Catholic Faith.", ";text-align:center")}
{_row("Sessio III.", "<i>Published in the Third Session held April</i> 24, 1870.", ";text-align:center")}
{_row("PIUS EPISCOPUS", "PIUS, BISHOP, SERVANT OF THE SERVANTS OF GOD.", ";text-align:center")}
{_row("Dei Filius et generis humani Redemptor, Dominus Noster, quae non est", "Our Lord Jesus Christ promised that he would be with the Church, and his words: 'My Spirit that is in thee shall not depart.'<note place='foot' n='1'><p>Isaiah lix. 21.</p></note> He placed over the universal", ";text-indent:1em")}
</table>
<pb n="235" id="v.ii.i-Page_235" />
<table>
{_row("Ecclesiam et est", "Church the blessed Peter.<note place='foot' n='2'><p>From Sermon IV. chap. ii. of St. Leo the Great.</p></note> So it is.")}
{_row("Caput I.", "Chapter I.", ";text-align:center")}
{_row("De Deo", "Of God, the Creator of all Things.", ";text-align:center")}
{_row("Sancta catholica", "The holy Catholic Church believes that there is one true and living God.", ";text-indent:1em")}
{_row("Canones.", "Canons.", ";text-align:center")}
{_row("I.", "I.", ";text-align:center")}
{_row("De Deo", "Of God, the Creator of all things.", ";text-align:center")}
{_row("1. Si quis", "1. If any one shall deny one true God: let him be anathema.", ";text-indent:1em")}
{_row("2. Si quis", "2. If any one shall say that nothing exists but matter: let him", ";text-indent:1em")}
{_row("anathema sit", "be anathema.")}
{_row("Itaque", "Therefore, we entreat all the faithful.", ";text-indent:1em")}
</table>
</div3></div2></ThML.body></ThML>
"""


def _schaff_doc(tmp_path, monkeypatch):
    monkeypatch.setattr(schaff, "CORRECTIONS", ())     # they name words of the real file
    path = tmp_path / "creeds2.xml"
    path.write_text(SCHAFF_XML, encoding="utf-8")
    return schaff.build_schaff(VATICAN_I, "doc-id", "councils/ecum-20-first-vatican-council",
                               str(path))


def test_schaff_keeps_english_cell_only(tmp_path, monkeypatch):
    doc = _schaff_doc(tmp_path, monkeypatch)
    text = " ".join(p.content for p in doc.passages)
    assert "Our Lord Jesus Christ" in text and "If any one shall deny" in text
    for latin in ("Dei Filius et generis", "quae non est", "Si quis", "anathema sit", "Itaque"):
        assert latin not in text
    # Schaff's headings and Manning's session line are labels, not text.
    assert "Published in the Third Session" not in text and "Canons." not in text
    assert [p.anchor for p in doc.passages] == [f"first-vatican-council/dei-filius/{u}" for u in (
        "prologue", "chapter-1", "canons-1/canon-1", "canons-1/canon-2", "conclusion")]
    assert [p.chapter_label for p in doc.passages][1:3] == [
        "Dei Filius, Chapter I: Of God, the Creator of all Things",
        "Dei Filius, Canons I: Of God, the Creator of all things"]
    assert doc.passages[2].content == "If any one shall deny one true God: let him be anathema."
    assert doc.passages[2].reference == "First Vatican Council, Dei Filius, Canon I.1"


def test_schaff_joins_english_across_page_tables(tmp_path, monkeypatch):
    doc = _schaff_doc(tmp_path, monkeypatch)
    prologue = doc.passages[0]
    assert prologue.content.split("\n\n") == [
        "Pius, Bishop, Servant of the Servants of God.",
        "Our Lord Jesus Christ promised that he would be with the Church, and his words: "
        "'My Spirit that is in thee shall not depart.' He placed over the universal Church "
        "the blessed Peter. So it is."]
    assert prologue.metadata["pages"] == ["234", "235"]
    # The scripture note stays as a footnote after its word; Schaff's other note goes.
    note, = prologue.metadata["footnotes"]
    assert note["text"] == "Isaiah lix. 21."
    assert prologue.content[:note["at"]].endswith("shall not depart.'")
    assert "Leo the Great" not in prologue.content
    # A canon running on into the next cell stays one canon.
    assert doc.passages[3].content == "If any one shall say that nothing exists but matter: let him be anathema."


@pytest.mark.skipif(not _vendored, reason="needs the vendored councils")
def test_schaff_prints_both_constitutions_whole():
    doc = _built("First Vatican Council")
    units = _units(doc)
    df = [u for u in units if "/dei-filius/" in u]
    pa = [u for u in units if "/pastor-aeternus/" in u]
    assert [u for u in df if "/chapter-" in u] == [
        f"first-vatican-council/dei-filius/chapter-{n}" for n in range(1, 5)]
    assert [u.split("/dei-filius/")[1] for u in df if "/canons-" in u] == [
        f"canons-{g}/canon-{n}" for g, k in ((1, 5), (2, 4), (3, 6), (4, 3)) for n in range(1, k + 1)]
    assert pa == ["first-vatican-council/pastor-aeternus/prologue"] + [
        f"first-vatican-council/pastor-aeternus/chapter-{n}" for n in range(1, 5)]
    chapter_4 = " ".join(p.content for p in doc.passages
                         if p.anchor.startswith("first-vatican-council/pastor-aeternus/chapter-4"))
    assert "is possessed of that infallibility" in chapter_4
    # CCEL heads Pastor Aeternus's first chapter "Chapter IV."; the print reads "Chapter I.".
    first = next(p for p in doc.passages if p.anchor.endswith("/pastor-aeternus/chapter-1"))
    assert first.unit_label == "Chapter I"
    assert "true and good" in " ".join(p.content for p in doc.passages)   # CORRECTIONS
    assert doc.metadata["held_text_url"] == VATICAN_I["url"]
    assert doc.translation == schaff.TRANSLATION


@pytest.mark.skipif(not _vendored, reason="needs the vendored councils")
def test_schaff_passages_hold_no_latin_and_no_editors_notes():
    latin = {"et", "est", "quae", "non"}
    for p in _built("First Vatican Council").passages:
        words = re.findall(r"[a-zæœ]+", p.content.lower())
        assert sum(w in latin for w in words) <= 0.05 * len(words), p.anchor
        for note in p.metadata.get("footnotes", []):
            assert scripture_reference(note["text"]) == note["text"], p.anchor
            assert re.search(r"\w[.,;:'!?]*$", p.content[:note["at"]]), (p.anchor, note)
        assert not re.search(r"Labbe|Benedictine|From the (?:Acts|Bull|Brief|letter|Formula)",
                             p.content), p.anchor


def test_tanners_vatican_i_goes_where_its_text_went():
    reg = work_registry.current()
    v = "first-vatican-council"
    open_ = {r["old_anchor"]: r["new_anchor"] for r in reg.redirects if not r.get("closed_by")}
    assert open_[f"{v}/sec-8/5"] == f"{v}/dei-filius/chapter-1"
    assert open_[f"{v}/sec-15/9"] == f"{v}/dei-filius/conclusion"
    removed = {e["anchor"]: e for e in work_registry.open_removals(reg)}
    assert removed[f"{v}/sec-1/1"]["reason"] == "rule-g-editorial"
    for anchor, gap in ((f"{v}/sec-3/2", "G10"), (f"{v}/sec-5/3", "G11")):
        assert removed[anchor]["reason"] == "translation-in-preparation"
        assert f"(gap {gap})" in removed[anchor]["detail"]
        assert removed[anchor]["tombstone"] == "This text is not available on TheoCorpus at present."
    rows = [r for r in reg.passages if r["document_id"] == "5c3cb0a3-883a-5f43-a747-b5e7196e68e1"]
    assert not [r["anchor"] for r in rows if r["status"] == "active" and "/sec-" in r["anchor"]]


def test_vatican_i_rights_row_is_schaffs():
    rows = [r for r in rights_inventory.load()
            if r["document_id"] == "5c3cb0a3-883a-5f43-a747-b5e7196e68e1"]
    row, = rows
    assert row["source_path"] == "councils/creeds2.xml" and row["status"] == "pd-us-non-renewal"
    assert row["planned_for"] is None


# --- 1.2c: councils 1 to 7 from Percival ---------------------------------------------------------

from ingest import councils_percival as percival  # noqa: E402

PERCIVAL_XML = """<?xml version="1.0"?>
<ThML><ThML.body>
<div1 id="v" title="The Council of Example.">
<div2 id="v.i" title="Historical Introduction."><p id="v.i-p1" class="c18">The council met in a city.</p></div2>
<div2 id="v.ii" title="The Canons.">
<div3 id="v.ii.i" title="Canon I.">
<p id="v.ii.i-p1" class="c14">The Canons of the Council.</p>
<p id="v.ii.i-p2" class="c34">Canon I.</p>
<p id="v.ii.i-p3" class="c18">Let no bishop leave his see without the consent of the synod<note n="1" id="v.ii.i-p3.1">Some read "province".</note> of the province.</p>
<p id="v.ii.i-p4" class="c31">Notes.</p>
<p id="v.ii.i-p5" class="c30">Ancient Epitome of Canon I.</p>
<p id="v.ii.i-p6" class="c35">A bishop shall not leave his see.</p>
<p id="v.ii.i-p7" class="c36">Zonaras.</p>
<p id="v.ii.i-p8" class="c18">This canon was often renewed.</p>
</div3>
<div3 id="v.ii.ii" title="Excursus on Sees."><p id="v.ii.ii-p1" class="c18">An excursus on sees.</p></div3>
<div3 id="v.ii.iii" title="Canon II.">
<p id="v.ii.iii-p1" class="c46">Canon II.</p>
<p id="v.ii.iii-p1a" class="c35">That the clergy are to obey.</p>
<p id="v.ii.iii-p2" class="c18">(Probably adopted at a later council.)</p>
<p id="v.ii.iii-p3" class="c18">Let the clergy obey their bishop.</p>
<p id="v.ii.iii-p4" class="c31">Notes.</p>
<p id="v.ii.iii-p5" class="c18">Van Espen remarks on it.</p>
</div3>
</div2>
<div2 id="v.iii" title="The Synodal Letter.">
<p id="v.iii-p1" class="c14">The Synodal Letter.</p>
<p id="v.iii-p2" class="c31">(Found in Labbe, Concilia, Tom. II.)</p>
<p id="v.iii-p3" class="c18">To the Church of the city, greeting.</p>
<p id="v.iii-p3a" class="c35">The Creed of the Fathers.</p>
<p id="v.iii-p4" class="c19">[Next was read the letter of the emperor.]</p>
<p id="v.iii-p5" class="c19">We have decreed what is written above.</p>
</div2>
</div1>
</ThML.body></ThML>"""
EXAMPLE = {"council": "Council of Example", "year": 400, "council_number": 1,
           "url": "https://www.papalencyclicals.net/councils/ecum01.htm",
           "file": "ecum-01-council-of-example.html"}
EXAMPLE_TEXTS = [*percival._canons("v.ii", ["i", "iii"]),
                 percival.Text("synodal-letter", "The Synodal Letter", "synodal-letter",
                               "The Synodal Letter", "v.iii")]


def _example(tmp_path, monkeypatch):
    path = tmp_path / "npnf.xml"
    path.write_text(PERCIVAL_XML, encoding="utf-8")
    monkeypatch.setattr(percival, "COUNCILS", {"Council of Example": EXAMPLE_TEXTS})
    return percival.build_percival(EXAMPLE, "doc-id", "councils/ecum-01-council-of-example",
                                   percival.read_divs(str(path)))


def test_percival_allowlist_drops_epitome_and_notes(tmp_path, monkeypatch):
    doc = _example(tmp_path, monkeypatch)
    text = " ".join(p.content for p in doc.passages)
    for editor in ("Historical", "Ancient Epitome", "Zonaras", "renewed", "excursus", "Van Espen",
                   "Probably adopted", "Found in", "Next was read", "province\"", "Some read",
                   "Canon II", "That the clergy"):
        assert editor not in text, editor
    assert [p.content for p in doc.passages] == [
        "Let no bishop leave his see without the consent of the synod of the province.",
        "Let the clergy obey their bishop.",
        "To the Church of the city, greeting.\n\nThe Creed of the Fathers.\n\n"
        "We have decreed what is written above."]


def test_percival_canon_anchors(tmp_path, monkeypatch):
    doc = _example(tmp_path, monkeypatch)
    assert [(p.anchor, p.reference, p.chapter_key) for p in doc.passages] == [
        ("council-of-example/canon/1", "Council of Example, Canon 1", "council-of-example/canons"),
        ("council-of-example/canon/2", "Council of Example, Canon 2", "council-of-example/canons"),
        ("council-of-example/synodal-letter", "Council of Example, The Synodal Letter",
         "council-of-example/synodal-letter")]
    assert all(p.metadata["text_replaced"] == percival.TEXT_REPLACED for p in doc.passages)
    assert doc.metadata["held_text_url"] == EXAMPLE["url"]


def test_percival_refuses_a_text_that_does_not_end_where_named(tmp_path, monkeypatch):
    monkeypatch.setattr(percival, "COUNCILS", {"Council of Example": [
        percival.Text("canon/1", "Canon 1", "canons", "Canons", "v.ii.i", last="p8")]})
    path = tmp_path / "npnf.xml"
    path.write_text(PERCIVAL_XML, encoding="utf-8")
    with pytest.raises(ValueError, match="does not end at p8"):
        percival.build_percival(EXAMPLE, "doc-id", "k", percival.read_divs(str(path)))


# What the 1.2a inventory lists for each council, as Percival prints it (and R9's two texts).
PERCIVAL_UNITS = {
    "Council of Nicaea": ["creed", *[f"canon/{n}" for n in range(1, 21)], "synodal-letter"],
    "First Council of Constantinople": ["creed", "letter-to-theodosius",
                                        *[f"canon/{n}" for n in range(1, 8)], "synodical-letter"],
    "Council of Ephesus": ["cyril-second-letter", "nestorius-second-letter", "cyril-third-letter",
                           *[f"anathema/{n}" for n in range(1, 13)], "decree-against-nestorius",
                           "synodical-letter", *[f"canon/{n}" for n in range(1, 9)],
                           "letter-to-pamphylia", "letter-to-celestine",
                           "definition-against-the-messalians", "decree-on-euprepius-and-cyril",
                           "letter-to-john-of-antioch"],
    "Council of Chalcedon": ["tome-of-leo", "condemnation-of-dioscorus", "definition",
                             "decree-on-jerusalem-and-antioch", "decree-on-the-bishop-of-ephesus",
                             "decree-on-nicomedia", *[f"canon/{n}" for n in range(1, 31)]],
    "Second Council of Constantinople": ["sentence", *[f"anathema/{n}" for n in range(1, 15)]],
    "Third Council of Constantinople": ["sentence-against-the-monothelites", "definition",
                                        "letter-to-agatho"],
    "Second Council of Nicaea": ["definition", "anathemas", *[f"canon/{n}" for n in range(1, 23)],
                                 "letter-to-the-emperors"],
}
_PERCIVAL_BUILT: dict = {}


def _percival_built(council):
    if not _PERCIVAL_BUILT:
        for d in build_documents():
            if d.title in PERCIVAL_UNITS:
                _PERCIVAL_BUILT[d.title] = work_registry.apply_overrides(d)
    return _PERCIVAL_BUILT[council]


@pytest.mark.skipif(not _vendored, reason="needs the vendored councils")
@pytest.mark.parametrize("council", PERCIVAL_UNITS)
def test_percival_prints_every_text_the_inventory_lists(council):
    doc = _percival_built(council)
    slug = re.sub(r"[^a-z0-9]+", "-", council.lower()).strip("-")
    assert _units(doc) == [f"{slug}/{u}" for u in PERCIVAL_UNITS[council]]
    assert doc.metadata["held_text_url"].startswith("https://www.papalencyclicals.net/councils/")


@pytest.mark.skipif(not _vendored, reason="needs the vendored councils")
@pytest.mark.parametrize("council", PERCIVAL_UNITS)
def test_percival_passages_hold_no_editors_matter(council):
    for p in _percival_built(council).passages:
        assert not re.search(r"Ancient Epitome|Excursus|Zonaras|Balsamon|Aristenus|Labbe|"
                             r"\(Found in|^Notes?\.|\[Section|\(\d{3}\)", p.content), p.anchor
        for note in p.metadata.get("footnotes", []):
            assert scripture_reference(note["text"]) == note["text"], p.anchor


@pytest.mark.parametrize("work", ["chrystal-ephesus", "hefele-nicaea-2"])
def test_percivals_scanned_texts_passed_the_gate_and_their_marks_balance(work):
    frozen = read_text(work)
    assert frozen["gate"] == "pass"
    text = " ".join(u["text"] for u in frozen["passages"])
    assert text.count("(") == text.count(")") and text.count("[") == text.count("]")
    assert _quotations_balance(text)
    assert not re.search(r"\(\d{3}\)|Section|[‘’]{2}|\b[A-Z]{2,} [A-Z]{2,} [A-Z]{2,}\b", text)


@pytest.mark.skipif(not _vendored, reason="needs the vendored councils")
def test_nestorius_letter_is_rejected_voice_and_hefeles_anathemas_say_where_they_come_from():
    letter = [p for p in _percival_built("Council of Ephesus").passages
              if p.anchor.startswith("council-of-ephesus/nestorius-second-letter")]
    assert len(letter) > 1 and all(p.voice == "rejected" for p in letter)
    assert all(p.metadata["text_source"] == "ocr" and p.metadata["scan_id"] == "authoritative01chry"
               for p in letter)
    assert letter[0].content.startswith("To the most religious and most dear-to-God")
    assert letter[-1].content.endswith("and to God most dear.")
    anathemas, = [p for p in _percival_built("Second Council of Nicaea").passages
                  if p.anchor == "second-council-of-nicaea/anathemas"]
    assert anathemas.note == "From Hefele's account of the session, in W. R. Clark's translation (1896)."
    assert anathemas.content.count("let him be anathema!") == 4
    assert "Chrystal" in _percival_built("Council of Ephesus").translation
    others = [p for d in PERCIVAL_UNITS for p in _percival_built(d).passages
              if p.voice and not p.anchor.startswith("council-of-ephesus/nestorius-second-letter")]
    assert not others


@pytest.mark.skipif(not _vendored, reason="needs the vendored councils")
def test_chalcedons_canons_29_and_30_say_they_were_not_enacted_as_canons():
    # Passages of the fourth session's minutes that later Greek collections count as
    # canons (Carter, 10 Nov 2026).
    canons = {p.anchor: p for p in _percival_built("Council of Chalcedon").passages}
    for n in (29, 30):
        assert canons[f"council-of-chalcedon/canon/{n}"].note == (
            "Not enacted as a canon: a passage from the minutes of the fourth session, which "
            f"later Greek collections count as canon {n}.")
    assert all(canons[f"council-of-chalcedon/canon/{n}"].note is None for n in range(1, 29))
    assert "Apostolic throne [of Rome], said" in canons["council-of-chalcedon/canon/30"].content
    assert not re.search(r"Ancient Epitome|Hefele|From the Fourth Session",
                         canons["council-of-chalcedon/canon/29"].content)


def test_tanners_councils_1_to_7_go_where_their_text_went():
    reg = work_registry.current()
    # A live passage that was one whole canon or anathema keeps its ID under the new anchor.
    kept = {r["live_anchor"]: r["anchor"] for r in reg.passages if r["status"] == "active"
            and "/sec-" in r["live_anchor"] and r["anchor"] != r["live_anchor"]}
    assert kept["first-council-of-constantinople/sec-5/8"] == "first-council-of-constantinople/canon/1"
    assert kept["council-of-ephesus/sec-5/12"] == "council-of-ephesus/anathema/12"
    assert kept["second-council-of-nicaea/sec-26/26"] == "second-council-of-nicaea/canon/22"
    assert kept["council-of-chalcedon/sec-3/19"] == "council-of-chalcedon/canon/30"
    open_ = {r["old_anchor"]: r["new_anchor"] for r in reg.redirects if not r.get("closed_by")}
    assert open_["council-of-ephesus/sec-3/3"] == "council-of-ephesus/nestorius-second-letter"
    assert open_["council-of-nicaea/sec-2/2"] == "council-of-nicaea/creed"
    removed = {e["anchor"]: e for e in work_registry.open_removals(reg)}
    assert removed["council-of-nicaea/sec-1/1"]["reason"] == "rule-g-editorial"
    assert removed["second-council-of-nicaea/sec-26/27"]["reason"] == "debris"
    gap = removed["second-council-of-constantinople/sec-3/9"]
    assert gap["reason"] == "translation-in-preparation" and "(gap G13)" in gap["detail"]
    docs = {percival_document_id(c) for c in PERCIVAL_UNITS}
    assert not [r["anchor"] for r in reg.passages
                if r["document_id"] in docs and r["status"] == "active" and "/sec-" in r["anchor"]]


def percival_document_id(council):
    row, = [r for r in rights_inventory.load()
            if r["work"] == council and r["source_path"] == "councils/npnf214.xml"]
    return row["document_id"]


def test_councils_1_to_7_rights_rows_are_percivals():
    rows = [r for r in rights_inventory.load()
            if r["collection"] == "councils" and r["work"] in PERCIVAL_UNITS]
    assert {r["source_path"] for r in rows} == {"councils/npnf214.xml"}
    assert all(r["document_id"] and r["status"] == "pd-us-pre-1931" and r["planned_for"] is None
               for r in rows)
    also = {r["work"]: [a["source_path"] for a in r.get("also_from", [])] for r in rows}
    assert also["Council of Ephesus"] == ["councils/authoritative01chry/"]
    assert also["Second Council of Nicaea"] == ["councils/ahistoryofthecou05hefeuoft/"]


# --- 1.2b: Trent from Waterworth -----------------------------------------------------------

from ingest import councils_trent as trent  # noqa: E402
from normalize.text import clean_text  # noqa: E402

TRENT = {"council": "Council of Trent", "document": "Council of Trent", "year": 1563,
         "group": "ecumenical-1-20", "file": "ecum-19-council-of-trent.html",
         "url": "https://www.papalencyclicals.net/councils/trent/the-complete-text.htm"}
TRENT_ID = "e33e591b-9e2e-5059-974f-28c8e4ab6aae"

# The page's markup: bare text after a <center> and between <br>s, headings as <center>
# lines or paragraphs of their own, the print's page numbers in <strong>.
TRENT_HTML = """<html><body><article><div class="entry-content">
<p><strong>[Page 1]</strong></p>
<p></p><center>THE BULL OF INDICTION<br/>
OF THE SACRED ECUMENICAL AND GENERAL COUNCIL OF TRENT</center>PAUL, bishop, servant of the servants of God, for the future memory hereof.
<p>At the beginning of this our pontificate we would fain have remedied the evils, in order to <strong>[Page 2]</strong> maintain the Christian religion.</p>
<p>Blosius.</p>
<p><center>SESSION THE SIXTH,</center>Celebrated on the thirteenth day of the month of January, 1547.</p>
<p><center>DECREE ON JUSTIFICATION</center><center>Proem.</center>Whereas there is, at this time, a certain erroneous doctrine disseminated touching Justification.</p>
<p><center>CHAPTER I.<br/>
On the Inability of Nature and of the Law to justify man.</center>The holy Synod declares first, that all men had lost their innocence.<br/>
<br/>
Bare text that the page sets between breaks, with no paragraph of its own.</p>
<p>CHAPTER II.</p>
<p>On the dispensation and mystery of Christ's advent.</p>
<p>Whence it came to pass, that the heavenly Father sent unto men Jesus Christ.</p>
<p><center>ON JUSTIFICATION</center>CANON I.-If any one saith, that man may be justified by his own works; let him be anathema.</p>
<p>CANON II.-lf any one saith, that the grace of God is given only for this; let him be anathema.</p>
<p>Web content composed with the free online wysiwyg HTML editor. Please subscribe for a membership to remove promotional messages from the edited documents.</p>
<p><center>INDICTION OF THE NEXT SESSION</center>Doth it please you, that the next ensuing Session be celebrated on the Thursday?</p>
<p><center>SESSION THE SEVENTH,</center>Celebrated on the third day of the month of March, MDXLVII.</p>
<p><center>DECREE ON THE SACRAMENTS</center>Proem.</p>
<p>For the completion of the salutary doctrine on Justification, it hath seemed suitable to treat of the Sacraments.</p>
<p><center>ON THE SACRAMENTS IN GENERAL</center>CANON I.-If any one saith, that the sacraments of the New Law were not all instituted by Jesus Christ; let him be anathema.</p>
</div></article></body></html>"""


def _trent():
    return trent.build_trent(TRENT, BeautifulSoup(TRENT_HTML, "lxml"), TRENT_ID,
                             "councils/ecum-19-council-of-trent")


def test_trent_bare_text_between_br_is_kept():
    by = {p.anchor: p for p in _trent().passages}
    assert by["council-of-trent/bulls/indiction"].content.split("\n\n") == [
        "PAUL, bishop, servant of the servants of God, for the future memory hereof.",
        "At the beginning of this our pontificate we would fain have remedied the evils, in "
        "order to maintain the Christian religion.",
        "Blosius."]
    chapter = by["council-of-trent/session-6/decree-on-justification/chapter-1"]
    assert chapter.content.split("\n\n") == [
        "On the Inability of Nature and of the Law to justify man.",
        "The holy Synod declares first, that all men had lost their innocence.",
        "Bare text that the page sets between breaks, with no paragraph of its own."]
    # The print's page numbers become metadata; the site's advert goes (C-05).
    assert by["council-of-trent/bulls/indiction"].metadata["pages"] == ["1", "2"]
    text = " ".join(p.content for p in by.values())
    assert "[Page" not in text and "wysiwyg" not in text


def test_trent_center_headings_become_structure():
    doc = _trent()
    assert doc.author == "Council of Trent" and doc.translation == trent.TRANSLATION
    s6, s7 = "council-of-trent/session-6", "council-of-trent/session-7"
    assert [p.anchor for p in doc.passages] == [
        "council-of-trent/bulls/indiction",
        f"{s6}/decree-on-justification/proem",
        f"{s6}/decree-on-justification/chapter-1",
        f"{s6}/decree-on-justification/chapter-2",
        f"{s6}/canons-on-justification/canon-1",
        f"{s6}/canons-on-justification/canon-2",
        f"{s6}/indiction-of-the-next-session",
        f"{s7}/decree-on-the-sacraments/proem",
        f"{s7}/canons-on-the-sacraments-in-general/canon-1"]
    by = {p.anchor: p for p in doc.passages}
    proem = by[f"{s6}/decree-on-justification/proem"]
    # The session's dating line opens its first document.
    assert proem.content.startswith("Celebrated on the thirteenth day")
    assert proem.chapter_key == f"{s6}/decree-on-justification"
    assert proem.chapter_label == "Session 6: Decree on Justification"
    # A chapter set as a paragraph, with its title in the next one.
    second = by[f"{s6}/decree-on-justification/chapter-2"]
    assert second.unit_label == "Chapter II"
    assert second.content.startswith("On the dispensation and mystery of Christ's advent.\n\n")
    assert second.reference == "Council of Trent, Session 6, Decree on Justification, Chapter II"
    assert by[f"{s7}/decree-on-the-sacraments/proem"].content.startswith(
        "Celebrated on the third day of the month of March, MDXLVII.\n\nFor the completion")


def test_trent_canon_anchor_includes_session():
    by = {p.anchor: p for p in _trent().passages}
    first = by["council-of-trent/session-6/canons-on-justification/canon-1"]
    other = by["council-of-trent/session-7/canons-on-the-sacraments-in-general/canon-1"]
    assert first.id != other.id or first.anchor != other.anchor
    assert first.unit_label == "Canon I"
    assert first.chapter_label == "Session 6: Canons on Justification"
    assert first.reference == "Council of Trent, Session 6, Canons on Justification, Canon I"
    assert first.content == ("If any one saith, that man may be justified by his own works; "
                             "let him be anathema.")
    # The page's "lf" for "If".
    assert by["council-of-trent/session-6/canons-on-justification/canon-2"].content.startswith(
        "If any one saith, that the grace of God")
    assert other.reference == ("Council of Trent, Session 7, Canons on the Sacraments in "
                               "General, Canon I")


def _trent_built():
    return _built("Council of Trent")


@pytest.mark.skipif(not _vendored, reason="needs the vendored councils")
def test_trent_parses_every_session_and_keeps_its_text():
    doc = _trent_built()
    units = _units(doc)
    sessions = {int(m.group(1)) for u in units
                if (m := re.match(r"council-of-trent/session-(\d+)/", u))}
    assert sessions == set(range(1, 26))
    count = lambda prefix, kind: sum(1 for u in units if u.startswith(
        f"council-of-trent/{prefix}/{kind}-"))
    assert count("session-6/decree-on-justification", "chapter") == 16
    assert count("session-6/canons-on-justification", "canon") == 33
    assert count("session-7/canons-on-the-sacraments-in-general", "canon") == 13
    assert count("session-13/decree-concerning-the-most-holy-sacrament-of-the-eucharist",
                 "chapter") == 8
    assert count("session-13/canons-on-the-most-holy-sacrament-of-the-eucharist", "canon") == 11
    assert [u for u in units if u.startswith("council-of-trent/bulls/")] == [
        f"council-of-trent/bulls/{b}" for b in
        ("indiction", "transfer", "resumption", "celebration", "confirmation")]
    # No anchor carries a collision suffix.
    assert not [u for u in units
                if not re.fullmatch(r"(?:chapter|canon)-\d+|[a-z-]*[a-z]", u.rsplit("/", 1)[1])]
    # At least 97% of the article's text, less the site's text and the headings.
    with open(os.path.join(_SRC, TRENT["file"]), "rb") as f:
        article = BeautifulSoup(f.read(), "lxml").find("div", class_="entry-content")
    blocks = [b for b in trent._blocks(article)
              if not trent._is_heading(b) and not trent._CHROME.search(b.text)]
    joined = re.sub(r"\s+", " ", " ".join(p.content for p in doc.passages))
    total = kept = 0
    for b in blocks:
        text = trent._CANON.sub(r"\2", clean_text(b.text))
        total += len(text)
        kept += len(text) * (text[3:] in joined)
    assert kept >= 0.97 * total, (kept, total)


@pytest.mark.skipif(not _vendored, reason="needs the vendored councils")
def test_trent_text_has_no_site_text_or_print_furniture():
    for p in _trent_built().passages:
        assert not re.search(r"\[Page \d+\]|wysiwyg|^CANON |^CHAPTER |This title is missing",
                             p.content), p.anchor


def test_trents_old_passages_follow_their_text():
    reg = work_registry.current()
    open_ = {r["old_anchor"]: r for r in reg.redirects if not r.get("closed_by")}
    t = "council-of-trent"
    # Canon numbers restarted in every session; each old canon goes to its own.
    assert open_[f"{t}/canon/ii"]["new_anchor"] == f"{t}/session-6/canons-on-justification/canon-2"
    assert open_[f"{t}/canon/ii-2"]["new_anchor"] == \
        f"{t}/session-7/canons-on-the-sacraments-in-general/canon-2"
    assert open_[f"{t}/canon/ii"]["kind"] == "moved"
    assert open_[f"{t}/sec-0/29"]["new_anchor"] == \
        f"{t}/session-21/canons-on-communion-under-both-species/conclusion"
    removed = {e["anchor"]: e for e in work_registry.open_removals(reg)}
    advert = removed[f"{t}/sec-0/21"]
    assert (advert["reason"], advert["tombstone"]) == (
        "debris", "This card held website text, not the Council's.")
    rows = [r for r in reg.passages if r["document_id"] == TRENT_ID]
    old = [r for r in rows if re.match(rf"{t}/(?:sec-0|canon)/", r["anchor"])]
    assert len(old) == 192 and not [r for r in old if r["status"] == "active"]
    # Every old row is explained: a redirect, or the advert's removal.
    explained = set(r["old_passage_id"] for r in open_.values()) | {advert["passage_id"]}
    assert not [r["anchor"] for r in old if r["passage_id"] not in explained]
