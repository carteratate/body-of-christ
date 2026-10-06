"""0.1b health rules. Runs in CI: every document is written here, and no vendored source
is read."""
import gzip
import json
from contextlib import asynccontextmanager

import pytest

import health
from checks import health as health_cli
from checks import report
from model import Document, Passage
from publication import CollectionPublicationRunner, PublicationRequest

GOOD = ("The Word was made flesh and dwelt among us, and we saw his glory, the glory as of "
        "the only begotten of the Father, full of grace and truth.")


def _p(content=GOOD, anchor="a", position=0, reference=None, chapter_key="ch-1",
       chapter_label="Chapter 1"):
    return Passage(content=content, reference=anchor if reference is None else reference,
                   anchor=anchor, chapter_key=chapter_key, chapter_label=chapter_label,
                   position=position)


def _doc(*passages, collection="encyclicals", doc_id="doc-1"):
    return Document(id=doc_id, collection=collection, title="A Document",
                    passages=list(passages))


def _one(content, collection="encyclicals"):
    """A document whose second passage holds `content`, after a good first passage."""
    return _doc(_p(anchor="a", position=0), _p(content, anchor="b", position=1),
                collection=collection)


def _rules(document, collection=None):
    return [v.rule for v in health.check_documents(collection or document.collection, [document])]


def _fires(rule, document, collection=None):
    return rule in _rules(document, collection)


def test_rules_are_the_spec_ids():
    assert health.BLOCK_RULES == ("H1_blank", "H2_debris", "H3_positions",
                                  "H4_anchor_unique", "H5_anchor_nonempty")
    assert health.REPORT_RULES == ("R1_short", "R2_footer", "R3_note_start", "R4_dup_text",
                                   "R5_repeated_reference", "R6_joined_paragraphs",
                                   "R7_non_english", "R8_anchor_suffix")


def test_good_document_has_no_violations():
    assert _rules(_doc(_p(anchor="a", position=0),
                       _p(GOOD.replace("Word", "Light"), anchor="b", position=1))) == []


# --------------------------------------------------------------------------- block rules

def test_h1_blank():
    assert _fires("H1_blank", _one("  \n\t "))
    assert not _fires("H1_blank", _one("x" + GOOD))


def test_h2_debris():
    for debris in (".", "12", "XIV.", "[3]", "- ", "(iv)", "“”"):
        document = _one(debris)
        assert _fires("H2_debris", document), debris
    assert not _fires("H2_debris", _one("XIV. Of charity."))
    # Blank text is H1's, not also H2's.
    assert _rules(_one("   ")).count("H2_debris") == 0


def test_h3_positions():
    assert _fires("H3_positions", _doc(_p(anchor="a", position=0), _p(anchor="b", position=2)))
    assert _fires("H3_positions", _doc(_p(anchor="a", position=1), _p(anchor="b", position=0)))
    assert _fires("H3_positions", _doc(_p(anchor="a", position=1)))
    assert not _fires("H3_positions", _doc(_p(anchor="a", position=0), _p(anchor="b", position=1)))


def test_h4_anchor_unique():
    document = _doc(_p(anchor="x", position=0), _p(GOOD + " Amen.", anchor="x", position=1))
    assert _rules(document).count("H4_anchor_unique") == 1
    assert not _fires("H4_anchor_unique", _doc(_p(anchor="x", position=0),
                                               _p(GOOD + " Amen.", anchor="y", position=1)))


@pytest.mark.parametrize("field", ["anchor", "chapter_key", "chapter_label"])
def test_h5_anchor_nonempty(field):
    passage = _p(anchor="b", position=1)
    setattr(passage, field, " ")
    assert _fires("H5_anchor_nonempty", _doc(_p(anchor="a", position=0), passage))
    assert not _fires("H5_anchor_nonempty", _one(GOOD + " Amen."))


def test_block_violations_have_block_severity_and_report_rules_report():
    document = _doc(_p("", anchor="a", position=0), _p("Short one", anchor="b", position=1))
    severities = {v.rule: v.severity for v in health.check_documents("encyclicals", [document])}
    assert severities == {"H1_blank": "block", "R1_short": "report"}


# --------------------------------------------------------------------------- report rules

def test_r1_short():
    assert _fires("R1_short", _one("PAUL VI"))
    assert not _fires("R1_short", _one("A heading long enough"))   # 21 characters
    assert not _fires("R1_short", _one("1975"))                     # no letter; H2's


def test_bible_and_canon_short_passages_are_allowed():
    assert _fires("R1_short", _one("Jesus wept.", collection="encyclicals"))
    for collection in ("bible", "canon-law"):
        assert not _fires("R1_short", _one("Jesus wept.", collection=collection)), collection


def test_r2_footer():
    for tail in ("\n(n: indicates that the text corresponds to a new version",
                 "\n[Earlier version]", "\n[Original version of can. 694]", "\n______________"):
        assert _fires("R2_footer", _one(GOOD + tail)), tail
    assert not _fires("R2_footer", _one(GOOD + " The__end."))


def test_r2_footer_reads_per_collection_patterns(monkeypatch):
    patterns = json.loads(json.dumps(health.load_patterns()))
    patterns["R2_footer"]["councils"] = [r"\bPage \d+ of \d+"]
    monkeypatch.setattr(health, "load_patterns", lambda: patterns)
    footer = GOOD + " Page 3 of 9"
    assert _fires("R2_footer", _one(footer, collection="councils"))
    assert not _fires("R2_footer", _one(footer, collection="encyclicals"))


def test_r3_note_start():
    for note in ("Cf. Lumen Gentium, 25.", "cf. Pius XII, Mystici Corporis: AAS 35 (1943).",
                 "Ibid., 27; and the rest.", "See the note of Maranus.",
                 "See Cave’s Primitive Christianity, p. 132.", "Eph. 1:10). And so on.",
                 "Lk 1: 31-37).16 It may be easy", "John 2:22; 12:16; cf. 14:26.",
                 "Jn. 1:14. 2. Jn. 3:16. 3. Heb. 1:1-2.", "Nm 11.11,14. 2. Rom 1.12."):
        assert _fires("R3_note_start", _one(note)), note
    for prose in ("See how great a love the Father has given us.", "See Jesus as happy.",
                  "John 3:16 is the verse most often quoted.",
                  "Seeing this, they wept.", GOOD):
        assert not _fires("R3_note_start", _one(prose)), prose


def test_r3_scripture_is_never_a_note():
    assert not _fires("R3_note_start", _one("See how good and how pleasant it is.",
                                            collection="bible"))
    assert not _fires("R3_note_start", _one("Cf. nothing.", collection="bible"))


def test_r4_dup_text():
    document = _doc(_p(anchor="a", position=0), _p("  " + GOOD.upper(), anchor="b", position=1))
    found = [v for v in health.check_documents("encyclicals", [document])
             if v.rule == "R4_dup_text"]
    assert [(v.anchor, v.detail) for v in found] == [("b", "same text as a")]
    short = "Amen, amen, I say to you."
    assert not _fires("R4_dup_text", _doc(_p(short, anchor="a", position=0),
                                          _p(short, anchor="b", position=1)))
    # Another document's copy is not a duplicate.
    other = _doc(_p(anchor="a", position=0), doc_id="doc-2")
    assert not [v for v in health.check_documents("encyclicals", [_doc(_p()), other])
                if v.rule == "R4_dup_text"]


def test_r5_repeated_reference():
    document = _doc(_p(anchor="a", position=0, reference="§4"),
                    _p(GOOD + " Amen.", anchor="b", position=1, reference="§4"),
                    _p(GOOD + " Alleluia.", anchor="c", position=2, reference="§5"))
    assert [v.anchor for v in health.check_documents("encyclicals", [document])
            if v.rule == "R5_repeated_reference"] == ["a", "b"]
    assert not _fires("R5_repeated_reference", _one(GOOD + " Amen."))


def test_r6_joined_paragraphs():
    found = [v for v in health.check_documents(
        "apostolic-exhortations",
        [_one("convoked a special consecration.The Synod was a gift. It is so.Then more.")])
        if v.rule == "R6_joined_paragraphs"]
    assert [v.detail for v in found] == ["2 joins"]
    for fine in ("John P. McCormick, S.S., Ph.D., Rector of it.", "(cf.Rom. 5:5) and St.Gregory.",
                 "e.g.The case.", "U.S.A. Then. A sentence. Another one."):
        assert not _fires("R6_joined_paragraphs", _one(fine)), fine


def test_r7_non_english():
    italian = ("Quando giunse a Parigi l’indulto apostolico relativo ad alcune facoltà, i "
               "Vescovi, con devota e scrupolosa obbedienza, dichiararono di non sapere come "
               "regolarsi in questa incerta situazione, e chiesero consiglio alla Santa Sede.")
    assert _fires("R7_non_english", _one(italian))
    assert not _fires("R7_non_english", _one(GOOD + " " + GOOD))
    assert not _fires("R7_non_english", _one(italian[:150]))        # under 200 characters


def test_r7_skips_notes_and_citation_lists():
    citations = ("Nm 11.11,14. 2. Rom 1.12. 3. 2 Pt 3.11. 4. Ez 13.5. 5. Eph 4.3. 6. 1 Pt 5.2. "
                 "7. Jn 10.11. 8. Mt 5.14. 9. Lk 12.42. 10. Acts 20.28. 11. Phil 2.21. 12. "
                 "Col 1.24. 13. Heb 13.17. 14. Jas 5.16.")
    assert not _fires("R7_non_english", _one(citations))
    note = "Cf. " + ("Conciliorum collectio regia maxima, tomus " * 6)
    rules = _rules(_one(note))
    assert "R3_note_start" in rules and "R7_non_english" not in rules


def test_r8_anchor_suffix():
    assert _fires("R8_anchor_suffix", _doc(_p(anchor="cur-deus-homo/chapter-i--2")))
    assert not _fires("R8_anchor_suffix", _doc(_p(anchor="cur-deus-homo/chapter-i/p2")))


# --------------------------------------------------------------------------- check ids

def test_check_id_names_rule_collection_document_and_anchor():
    blank = health.check_documents("summa", [_doc(_p("", anchor="q1/a1"), collection="summa")])[0]
    assert blank.check_id == "health.H1_blank:summa/doc-1#q1/a1"
    gap = health.check_documents("summa", [_doc(_p(position=3), collection="summa")])[0]
    assert gap.check_id == "health.H3_positions:summa/doc-1"
    assert report.check_scope(blank.check_id) == "summa"
    # An empty or shared anchor adds the position, so each id still names one passage.
    shared = _doc(_p("", anchor="x", position=0), _p("", anchor="x", position=1),
                  _p("", anchor="", position=2), collection="summa")
    ids = [v.check_id for v in health.check_documents("summa", [shared]) if v.rule == "H1_blank"]
    assert ids == ["health.H1_blank:summa/doc-1#x@0", "health.H1_blank:summa/doc-1#x@1",
                   "health.H1_blank:summa/doc-1#@2"]
    assert report.check_scope(gap.check_id) == "summa"


# --------------------------------------------------------------------------- publish gate

def _runner(events, documents):
    @asynccontextmanager
    async def acquire(name):
        events.append(f"{name}:acquire")
        yield None

    return CollectionPublicationRunner(
        source_adapters={"encyclicals": lambda: documents},
        acquire_reader_store=lambda: acquire("reader"),
        acquire_search_index=lambda: acquire("search"),
    )


async def test_block_rule_refuses_before_store_acquisition():
    events: list[str] = []
    runner = _runner(events, [_doc(_p(anchor="a", position=0), _p(".", anchor="b", position=1))])
    with pytest.raises(ValueError, match=r"REFUSING: 1 health block-rule violations in "
                                         r"'encyclicals': H2_debris doc-1#b"):
        await runner.publish(PublicationRequest(collection="encyclicals"))
    assert events == []
    # A dry run builds through the same checks.
    with pytest.raises(ValueError, match="REFUSING"):
        runner.build(PublicationRequest(collection="encyclicals"))


def test_report_rules_never_refuse():
    events: list[str] = []
    runner = _runner(events, [_doc(_p("PAUL VI", anchor="a--2"))])
    assert len(runner.build(PublicationRequest(collection="encyclicals"))) == 1


def test_known_block_defect_is_accepted_and_a_new_one_is_not():
    document = _doc(_p(".", anchor="a", position=0), _p("12", anchor="b", position=1))
    known = {"health.H2_debris:encyclicals/doc-1#a"}
    with pytest.raises(ValueError, match=r"REFUSING: 1 health .*doc-1#b") as refused:
        health.refuse_block_violations("encyclicals", [document], known)
    assert "doc-1#a" not in str(refused.value)
    health.refuse_block_violations("encyclicals", [_doc(_p(".", anchor="a"))], known)


def test_refusal_lists_the_first_ten():
    document = _doc(*[_p("", anchor=f"a{i}", position=i) for i in range(12)])
    with pytest.raises(ValueError) as refused:
        health.refuse_block_violations("encyclicals", [document], set())
    message = str(refused.value)
    assert message.startswith("REFUSING: 12 health block-rule violations")
    assert "doc-1#a9 " in message and "doc-1#a10 " not in message
    assert message.endswith("; and 2 more")


# --------------------------------------------------------------------------- report CLI

def _snapshot(tmp_path, rows):
    directory = tmp_path / "snapshot"
    directory.mkdir()
    with gzip.open(directory / "passages.jsonl.gz", "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return directory


def _row(anchor, position, content=GOOD, collection="summa", document_id="doc-s"):
    return {"id": f"id-{anchor}", "document_id": document_id, "collection": collection,
            "title": "Summa", "author": "Thomas", "anchor": anchor, "chapter_key": "q1",
            "chapter_label": "Question 1", "reference": anchor, "position": position,
            "content": content}


def test_snapshot_passages_are_read_in_position_order(tmp_path):
    directory = _snapshot(tmp_path, [_row("b", 1, GOOD + " Amen."), _row("a", 0), _row("c", 2, ""),
                                     _row("x", 0, collection="bible", document_id="doc-b")])
    documents = health_cli.load_snapshot(str(directory), ("summa",))
    assert list(documents) == ["summa"]
    assert [p.anchor for p in documents["summa"][0].passages] == ["a", "b", "c"]
    assert _rules(documents["summa"][0]) == ["H1_blank"]
    everything = health_cli.load_snapshot(str(directory / "passages.jsonl.gz"))
    assert set(everything) == {"bible", "summa"}
    # A requested collection with no rows gets an empty entry.
    assert health_cli.load_snapshot(str(directory), ("councils",)) == {"councils": []}


def test_snapshot_null_position_fails_h3(tmp_path):
    rows = [_row("a", 0), _row("b", None, GOOD + " Amen.")]
    documents = health_cli.load_snapshot(str(_snapshot(tmp_path, rows)))
    assert [p.anchor for p in documents["summa"][0].passages] == ["a", "b"]
    assert _rules(documents["summa"][0]) == ["H3_positions"]


def test_cli_merges_runs_and_keeps_collections_it_did_not_cover(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setattr(health_cli, "build", lambda collections: {
        c: [_doc(_p(anchor="a"), collection=c, doc_id=f"doc-{c}")] for c in collections})
    assert health_cli.main(["--collection", "encyclicals", "--out", str(out)]) == 0
    assert health_cli.main(["--collection", "councils", "--out", str(out)]) == 0
    directory = _snapshot(tmp_path, [_row("a", 0, ""), _row("b", 1, "PAUL VI")])
    assert health_cli.main(["--collection", "summa", "--out", str(out),
                            "--from-snapshot", str(directory)]) == 0

    data = json.loads((out / "health.json").read_text())
    assert set(data["build"]) == {"councils", "encyclicals"}
    assert set(data["snapshot"]) == {"summa"}
    assert data["snapshot"]["summa"]["counts"]["H1_blank"] == 1
    assert set(data["measured_on"]["build"]) == {"councils", "encyclicals"}
    md = (out / "health.md").read_text()
    assert "| Collection | Rule | Severity | Build | Live snapshot |" in md
    assert "| summa | H1_blank | block | – | 1 |" in md
    # Numbers and anchors only: no passage text reaches either file.
    assert "PAUL VI" not in md and "PAUL VI" not in (out / "health.json").read_text()
    assert GOOD[:30] not in md


def test_cli_fails_on_a_build_block_violation_not_known(tmp_path, monkeypatch):
    monkeypatch.setattr(health_cli, "build", lambda collections: {
        "encyclicals": [_doc(_p("", anchor="a"))]})
    assert health_cli.main(["--collection", "encyclicals", "--out", str(tmp_path)]) == 1
    md = (tmp_path / "health.md").read_text()
    assert "Build block violations not in known_defects.json: 1." in md
    assert "`health.H1_blank:encyclicals/doc-1#a`" in md
