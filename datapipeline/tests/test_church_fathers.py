import os
import re
from collections import defaultdict

import pytest

import registry
from checks import source_text
from ingest import church_fathers as cf
from ingest import stromata_chadwick
from ingest.common import _block_text, _display_terminal_char, iter_chapters
from ingest.church_fathers import build_documents, build_all

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "church-fathers")
pytestmark = [
    pytest.mark.sources,
    pytest.mark.skipif(not os.path.isdir(_SRC),
                       reason="church-fathers sources not vendored; run scripts/vendor_sources.py"),
]


def test_apostolic_fathers_splits_into_per_work_documents():
    path = os.path.join(_SRC, "apostolic fathers.xml")
    docs = build_documents(path)
    clement = [d for d in docs if d.author == "Clement of Rome"
               and "First Epistle" in d.title]
    assert clement, [(d.author, d.title) for d in docs][:10]
    d = clement[0]
    assert d.collection == "church-fathers"
    assert d.passages and d.passages[0].chapter_key
    assert not d.passages[0].content.lstrip().startswith("[")


def test_single_author_files_unchanged_author():
    path = os.path.join(_SRC, "confessions.xml")
    docs = build_documents(path)
    assert len(docs) == 1
    assert docs[0].author == "Augustine"


def test_city_of_god_is_one_document_with_books_as_chapters():
    path = os.path.join(_SRC, "city-of-god.xml")
    docs = build_documents(path)
    cog = [d for d in docs if d.title == "City of God"]
    assert len(cog) == 1, [d.title for d in docs]
    d = cog[0]
    assert d.author == "Augustine"
    # Book structure flattened into labels + metadata, not separate documents.
    assert any((p.metadata or {}).get("book", "").startswith("Book") for p in d.passages)
    assert any(" · " in p.chapter_label for p in d.passages)


def test_build_all_has_unique_ids_and_anchors():
    docs = build_all()
    ids = [d.id for d in docs]
    assert len(ids) == len(set(ids)), "duplicate document ids"
    for d in docs:
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"duplicate anchors in {d.title!r}"


def test_historical_filenames_resolve_to_the_original_ccel_volumes():
    expected = {
        "apostolic fathers.xml": "anf01",
        "second-century.xml": "anf02",
        "third-century.xml": "anf04",
        "third-century-2.xml": "anf05",
        "third-century-3.xml": "anf06",
        "third-fourth-century.xml": "anf07",
    }
    for filename, book_id in expected.items():
        with open(os.path.join(_SRC, filename), encoding="utf-8") as source:
            head = source.read(4_096)
        assert f"<bookID>{book_id}</bookID>" in head


def _cut_length(content: str) -> int:
    """A piece's length as the source spells it. Pieces are cut from the source text, and
    cleaning then spells each ligature out ("æ" to "ae", 1.10a); cutting the folded text
    instead would move piece anchors. Every "ae" and "oe" counts as one letter, so words
    such as "does" make the bound slightly lenient, never stricter."""
    return len(content) - len(re.findall(r"[AaOo]e", content))



def test_split_passages_have_complete_reader_boundaries():
    docs = build_all()
    # 127 after 1.8a, whose rule G took Asterius Urbanus's only passage, his Elucidation;
    # 128 since 1.8c parses his text and brings the document back; 142 since 1.8b splits
    # the two Augustine treatise volumes into their 16 works; 109 since 3.1 removes 33
    # works under rules A to C; 112 since 5.6a adds Basil's three works (NPNF2-08); 115
    # with Cyril's and Gregory of Nazianzus's (NPNF2-07); 120 with Leo's and Gregory the
    # Great's (NPNF2-12 and NPNF2-13).
    assert len(docs) == 120
    for doc in docs:
        groups = defaultdict(list)
        for passage in doc.passages:
            # Stromata III's English keeps the Latin pieces' bounds, and with them their
            # IDs (#399); the English runs longer than the Latin.
            assert _cut_length(passage.content) <= 4_000 or (
                (doc.id, passage.chapter_key) == (stromata_chadwick.STROMATA,
                                                  stromata_chadwick.BOOK))
            match = re.match(r"^(.*)/p(\d+)$", passage.anchor)
            if match:
                groups[match.group(1)].append((int(match.group(2)), passage))
        for parts in groups.values():
            parts.sort()
            for (_, passage), (_, following) in zip(parts, parts[1:]):
                assert _display_terminal_char(
                    passage.content, len(passage.content)
                ) in ".!?;:"
                assert not following.content[0].islower()


# --------------------------------------------------------------------------- 1.8c

@pytest.fixture(scope="module")
def fathers():
    return build_all()


@pytest.fixture(scope="module")
def unremoved():
    """The build without 3.1's removals (rules A to C), for the checks 1.8c made of works
    3.1 then removes."""
    reg = registry.current()
    previous = registry.activate(registry.WorkRegistry(
        reg.works, reg.passages, reg.redirects,
        [e for e in reg.removals if e.get("added_by") != "3.1"], reg.kept_text))
    try:
        return build_all()
    finally:
        registry.activate(previous)


def _doc(docs, source_key):
    return next(d for d in docs if d.metadata["source_key"] == f"church-fathers/{source_key}")


def _work_div(filename, div_id):
    root = cf._read_root(os.path.join(_SRC, filename))
    return next(e for e in root.iter() if e.get("id") == div_id), cf._build_parent_map(root)


_GENUINE = [f"apostolic fathers.xml#v.{n}" for n in ("ii", "iii", "iv", "v", "vi", "vii", "viii")]


def test_container_authors_resolved(fathers):
    authors = {d.author for d in fathers}
    assert {"Tertullian", "Anatolius of Alexandria", "Pierius of Alexandria",
            "Dionysius of Alexandria", "Hermas", "Anonymous"} <= authors
    assert not [a for a in authors if any(x in a for x in
                                          ("Minor Writers", "Part Fourth", "Appendix",
                                           "Pastor of Hermas"))]
    hermas = sorted(d.title for d in fathers if d.author == "Hermas")
    assert hermas == ["The Shepherd: Commandments", "The Shepherd: Similitudes",
                      "The Shepherd: Visions"]


def test_relabelled_documents_keep_their_frozen_ids(fathers):
    reg = registry.current()
    for d in fathers:
        frozen = reg.document_by_key.get(("church-fathers", d.metadata["source_key"]))
        assert frozen is None or frozen == d.id, d.title


def test_ignatius_letters_open_with_salutation(unremoved):
    # The 15 Ignatian letters that print a greeting above their first chapter; the
    # short letters to John and Mary carry theirs as the title, the Martyrdom has none.
    # Five are forgeries 3.1 removes (rule B), so the adapter is checked unremoved.
    fathers = unremoved
    opened = [d for d in fathers if d.author == "Ignatius"
              and d.passages[0].chapter_label == "Salutation"]
    assert len(opened) == 15, sorted(d.title for d in opened)
    for d in opened:
        assert d.passages[0].content.startswith("Ignatius"), d.title
        assert d.passages[0].anchor.endswith("/salutation")
    tarsians = next(d for d in opened if d.title == "Epistle to the Tarsians")
    assert "Church which is at Tarsus" in tarsians.passages[0].content
    for key in ("apostolic fathers.xml#iv.ii", "apostolic fathers.xml#iv.iv",
                "second-century.xml#v.ii"):
        assert _doc(fathers, key).passages[0].chapter_label in ("Salutation", "Opening")


def test_recension_split_one_paragraph_per_chapter(fathers):
    reg = registry.current()
    for key in _GENUINE:
        d = _doc(fathers, key)
        assert d.id == reg.document_by_key[("church-fathers", f"church-fathers/{key}")]
        assert not d.title.endswith("Versions")
        units = [p.anchor.split("/")[0] for p in d.passages]
        assert len(units) == len(set(units)), d.title
        assert all(p.anchor.endswith(("/short", "/salutation")) for p in d.passages)
        for p in d.passages:
            assert p.content.count("who is also called Theophorus") <= 1, p.anchor


def test_every_old_recension_passage_has_split_redirect(fathers):
    reg = registry.current()
    redirects = {r["old_passage_id"]: r for r in registry.open_redirects(reg)}
    for key in _GENUINE:
        d = _doc(fathers, key)
        built = {p.anchor for p in d.passages}
        old = [r for r in reg.passages if r["document_id"] == d.id and r["anchor"] not in built]
        assert old, d.title
        for r in old:
            target = redirects[r["passage_id"]]
            assert target["new_anchor"].endswith("/short") and target["new_anchor"] in built
            assert target["kind"] in ("split", "merged"), target


def test_long_recension_spans_in_removal_registry(fathers):
    reg = registry.current()
    spans = {e["span"]["sha1"]: e for e in reg.removals
             if e["scope"] == "span" and e["reason"] == "rule-b"}
    count = 0
    for key in _GENUINE:
        filename, div = key.split("#")
        work, parent_map = _work_div(filename, div)
        d = _doc(fathers, key)
        for unit in [work] + [elem for _, elem in iter_chapters(work, parent_map)]:
            for block in cf.recension_blocks(unit)[1]:
                text = source_text._thml_text(block, skip_notes=True)
                e = spans[source_text._paragraph_sha1(text)]
                assert e["document_id"] == d.id and e["church_act"] is None
                assert "scholarship" in e["detail"]
                assert " ".join(_block_text(block).split()) not in \
                    " ".join(" ".join(p.content for p in d.passages).split())
                count += 1
    assert count == 97          # 96 units printing both, and Ephesians' second chapter XX
    assert registry.validate(reg) == []


def test_peter_canons_have_no_commentary(fathers):
    d = _doc(fathers, "third-century-3.xml#ix.iv")
    assert d.title == "The Canonical Epistle"
    assert not [p.anchor for p in d.passages
                if "Balsamon" in p.content or "Zonaras" in p.content]
    assert len({p.chapter_key for p in d.passages}) == 15
    reg = registry.current()
    mine = [e for e in reg.removals if e["document_id"] == d.id and e["reason"] == "other-author"]
    spans = {e["span"]["sha1"] for e in mine if e["scope"] == "span"}
    anchors = {r["passage_id"]: r["anchor"] for r in reg.passages}
    retired = [e for e in mine if e["scope"] == "passage"]
    assert len(retired) == 13 and all(e["tombstone"] for e in retired)
    # Each opens on a commentator's paragraph of its canon (`<canon>/from-p<n>`).
    retired_canons = {anchors[e["passage_id"]].split("/from-")[0] for e in retired}
    work, _ = _work_div("third-century-3.xml", "ix.iv")
    for canon in [c for c in work if str(c.tag).startswith("div")]:
        for block in cf.commentary_blocks(canon)[1]:
            text = source_text._thml_text(block, skip_notes=True)
            assert source_text._paragraph_sha1(text) in spans, canon.get("id")
    # Every canon whose commentary opened a live passage of its own retires it.
    assert retired_canons <= {c.get("id") for c in work if str(c.tag).startswith("div")}


def test_container_passages_carry_work_key(fathers):
    reg = registry.current()
    rows = {(r["document_id"], r["anchor"]): r for r in reg.passages}
    entries = {w["document_id"]: w for w in reg.works}
    for key in ("third-century-3.xml#iii.iii", "third-century-3.xml#iii.iv",
                "third-century-2.xml#iv.iv", "third-century-2.xml#iv.vii"):
        d = _doc(fathers, key)
        keys = {w.work_key for w in d.works}
        assert keys and all(p.work_key in keys for p in d.passages), d.title
        assert [w["work_key"] for w in entries[d.id]["works"]] == [w.work_key for w in d.works]
        assert all(rows[(d.id, p.anchor)]["work_key"] == p.work_key for p in d.passages)


def test_asterius_has_text(fathers):
    d = _doc(fathers, "third-fourth-century.xml#v.ii")
    assert d.author == "Asterius Urbanus" and len(d.passages) >= 3
    assert "Having now for a very long" in d.passages[0].content
    assert not [p for p in d.passages if "Elucidation" in p.chapter_label]


def test_panegyric_labels(fathers, unremoved):
    d = _doc(fathers, "third-century-3.xml#iii.iii")
    # 3.1 removes the Panegyric to Origen under rule A; its labels are checked unremoved.
    assert not [p for p in d.passages if p.chapter_key.startswith("iii.iii.iv.")]
    whole = _doc(unremoved, "third-century-3.xml#iii.iii")
    assert [p for p in whole.passages if p.chapter_key.startswith("iii.iii.iv.")]
    assert not [p.chapter_label for p in whole.passages if "Argument" in p.chapter_label]


def test_cyprian_letters_credited_to_senders(fathers):
    d = _doc(fathers, "third-century-2.xml#iv.iv")
    works = {w.work_key: w for w in d.works}
    # Epistles XXV and XXIX, by Novatian, leave under rule A (3.1).
    removed = {"iv.iv.xxv", "iv.iv.xxix", "iv.iv.xxx"}
    for div, (sender, _) in cf._LETTER_SENDERS.items():
        pieces = [p for p in d.passages if p.work_key == div]
        assert bool(pieces) != (div in removed), div
        assert works[div].author == sender
    assert works["iv.iv.lxxiv"].author == "Firmilian of Caesarea"
    # Continuation pieces resolve to the letter too.
    assert len([p for p in d.passages if p.work_key == "iv.iv.lxxiv"]) > 1
    assert works["iv.iv.xxx"].author is None          # Novatian's: 3.1 removes it
    assert works["iv.iv.i"].author == "Cyprian"


def test_epitome_is_its_own_work(fathers):
    d = _doc(fathers, "third-fourth-century.xml#iii.ii")
    epitome = [p for p in d.passages if p.chapter_key.startswith("iii.ii.viii.")]
    assert epitome
    assert {p.work_key for p in epitome} == {"iii.ii.viii"}
    assert [w.title for w in d.works] == ["Epitome of the Divine Institutes"]
    assert all(p.chapter_label.startswith("Epitome · ") for p in epitome)
    assert all(p.reference.startswith("Epitome of the Divine Institutes, ") for p in epitome)
    assert not [p.reference for p in epitome if "The Divine Institutes" in p.reference]


def test_container_labels_name_their_work(fathers):
    d = _doc(fathers, "third-century-2.xml#iv.v")
    assert d.passages[0].chapter_label.startswith("On the Unity of the Church · ")
    letters = _doc(fathers, "third-century-2.xml#iv.iv")
    labels = {p.chapter_label for p in letters.passages if p.work_key == "iv.iv.lxxiv"}
    assert labels == {"Firmilian of Caesarea, to Cyprian · Epistle LXXIV"}
    assert {p.chapter_label for p in letters.passages if p.work_key == "iv.iv.i"} \
        == {"Epistle I"}


# --------------------------------------------------------------------------- 1.8b

_NPNF103 = "on-the-holy-trinity.xml"
_TREATISES = ["On the Holy Trinity", "The Enchiridion", "On the Catechising of the Uninstructed",
              "A Treatise on Faith and the Creed", "Concerning Faith of Things Not Seen",
              "On the Profit of Believing", "On the Creed", "On Continence",
              "On the Good of Marriage", "Of Holy Virginity", "On the Good of Widowhood",
              "On Lying", "Against Lying", "Of the Work of Monks", "On Patience",
              "On Care to Be Had for the Dead"]


def _npnf(fathers, *files):
    return [d for d in fathers if d.metadata["source_file"] in files]


def test_treatise_volumes_split_into_their_works(fathers):
    docs = _npnf(fathers, _NPNF103)
    assert [d.title for d in docs] == _TREATISES
    assert {d.author for d in docs} == {"Augustine"}
    by_title = {d.title: d.id for d in docs}
    # The two volumes' frozen IDs stay with the work holding most of each.
    assert by_title["On the Holy Trinity"] == "b270ebca-051e-5094-8370-758ad599d9ca"
    assert by_title["On Continence"] == "f39c025e-78a6-5737-a94f-7896c84fc857"
    reg = registry.current()
    for d in docs:
        assert reg.document_by_key[("church-fathers", d.metadata["source_key"])] == d.id


def test_no_duplicate_suffix_keys_in_npnf103(fathers):
    keys = [p.chapter_key for d in _npnf(fathers, _NPNF103) for p in d.passages]
    assert keys and not [k for k in keys if "--" in k]


def test_npnf_argument_paragraphs_dropped(fathers):
    docs = _npnf(fathers, "city-of-god.xml")
    assert {d.title for d in docs} == {"City of God", "On Christian Doctrine"}
    assert not [p.anchor for d in docs for p in d.passages
                if any(line.startswith("Argument") for line in p.content.split("\n\n"))]


def test_npnf_editorial_matter_gone(fathers):
    docs = _npnf(fathers, _NPNF103, "city-of-god.xml")
    texts = [(p.anchor, p.chapter_label, p.content) for d in docs for p in d.passages]
    for needle in ("Shedd", "Translator’s Preface", "Translated by", "Contents of Christian"):
        assert not [a for a, label, c in texts if needle in c or needle in label], needle
    # The books' own text was only title lines and the editors' summary.
    assert not [a for a, label, _ in texts if label.endswith("· Introduction")]
    assert not [a for a, _, c in texts if c.startswith("In which the unity and equality")]


def test_augustine_book_prefaces_kept(fathers):
    trinity = _doc(fathers, f"{_NPNF103}#iv.i")
    preface = next(p for p in trinity.passages if p.chapter_label == "Book II · Preface")
    assert preface.content.startswith("When men seek to know God")
    labels = {p.chapter_label for d in _npnf(fathers, "city-of-god.xml") for p in d.passages}
    assert {"Book V · Preface", "Book VI · Preface", "Book VII · Preface"} <= labels
    doctrine = _doc(fathers, "city-of-god.xml#v")
    assert [p.chapter_label for p in doctrine.passages[:2]] == [
        "Retractations II.4",
        "Preface: Showing that to teach rules for the interpretation of Scripture is not a "
        "superfluous task"]


def test_retractations_quotes_kept_and_labeled(fathers):
    docs = _npnf(fathers, _NPNF103, "city-of-god.xml")
    kept = [(d, p) for d in docs for p in d.passages
            if re.match(r"^Retractations [IV]+\.\d+$", p.chapter_label)]
    assert len(kept) >= 9
    assert {d.author for d, _ in kept} == {"Augustine"}
    assert all(p.metadata["from"] == "Retractations" for _, p in kept)
    lying = next(p for d, p in kept if d.title == "Against Lying")
    assert lying.chapter_label == "Retractations II.60"
    assert lying.content.startswith("Then also I wrote a Book against Lying")
    assert "From the Retractations" not in lying.content
    letter = next(p for p in _doc(fathers, f"{_NPNF103}#iv.i").passages
                  if p.chapter_label == "Letter to Aurelius")
    assert letter.content.startswith("To the most blessed Lord")


def test_editors_chapter_titles_move_to_labels(fathers):
    trinity = _doc(fathers, f"{_NPNF103}#iv.i")
    first = next(p for p in trinity.passages if p.chapter_key == "iv.i.iii.i")
    assert first.chapter_label.startswith("Book I · Chapter 1: This Work is Written Against")
    assert not first.content.startswith("Chapter")
    # City of God's chapter titles are the ancient capitula and stay in the text.
    city = _doc(fathers, "city-of-god.xml#iv")
    chapter = next(p for p in city.passages if p.chapter_key == "iv.ii.ii")
    assert chapter.content.startswith("Chapter 1.—")


def test_confessions_plain_callers_removed(fathers):
    confessions = _doc(fathers, "confessions.xml")
    p = next(p for p in confessions.passages if p.chapter_key == "viii.xi")
    assert "remains immutably. It is good" in p.content
    assert "my gooodness." in p.content
    assert not re.search(r"[a-z][.,]\d", p.content)


# ------------------------------------------------------------------ 1.8d: On the Incarnation

_INCARNATION = "cf235300-e37d-5a7a-a421-f50efff38355"


@pytest.fixture(scope="module")
def incarnation():
    docs = build_documents(os.path.join(_SRC, "npnf204.xml"))
    assert len(docs) == 1, [d.title for d in docs]      # the rest of the volume is 5.6a's
    return docs[0]


def test_incarnation_is_robertson(incarnation):
    d = incarnation
    assert (d.id, d.author, d.title) == (_INCARNATION, "Athanasius",
                                         "On the Incarnation of the Word")
    assert d.metadata["source_key"] == "church-fathers/npnf204.xml#vii.ii"
    assert "Whereas in what precedes we have drawn out" in d.passages[0].content
    assert not [p.anchor for p in d.passages if "In our former book" in p.content]
    keys = list(dict.fromkeys(p.chapter_key for p in d.passages))
    assert len(keys) == 57
    assert [next(p.chapter_label for p in d.passages if p.chapter_key == k) for k in keys] \
        == [f"Section {n}" for n in range(1, 58)]
    assert d.passages[0].reference == "On the Incarnation of the Word, Section 1"


def test_incarnation_section_summaries_stripped(incarnation):
    assert not [p.anchor for p in incarnation.passages if p.content.startswith("Introductory")]
    # No section number or analytical heading is left, nor the title and rule over §1.
    assert not [p.anchor for p in incarnation.passages if "§" in p.content]
    assert not incarnation.passages[0].content.startswith("On the Incarnation")
    second = next(p for p in incarnation.passages if p.chapter_key == "vii.ii.ii")
    assert second.content.startswith("Of the making of the universe")


def test_incarnation_section_five_keeps_its_opening(incarnation):
    # §5 prints no analytical heading: its div title is Athanasius's own first sentence,
    # which stays; only "§5." goes.
    five = next(p for p in incarnation.passages if p.chapter_key == "vii.ii.v")
    assert five.content.startswith("For God has not only made us out of nothing; but He "
                                   "gave us freely")


def test_incarnation_removals_recorded():
    from ingest import editorial
    with editorial.recording() as log:
        build_documents(os.path.join(_SRC, "npnf204.xml"))
    removed = [r for _, _, edit in log if hasattr(edit, "removed") for r in edit.removed]
    summaries = [r for r in removed if r.kind == "section-summary"]
    assert len(summaries) == 56
    assert all(r.text.startswith("§") for r in summaries)
    # The work's title and rule line over §1, and §5's number.
    headings = [r.text for r in removed if r.kind == "heading"]
    assert len(headings) == 3 and "§5." in headings
    assert "On the Incarnation of the Word." in headings


def test_volume_scope_matches_the_adapter():
    assert source_text.VOLUME_SCOPE == {
        **{f: tuple(works) for f, works in cf.VOLUME_WORKS.items()},
        **{f: tuple(w.div for w in works) for f, works in cf.NPNF_WORKS.items()}}


def test_incarnation_coverage_reads_only_its_work():
    units = source_text.thml_units(os.path.join(_SRC, "npnf204.xml"))
    assert units and all(u.unit_id == "vii.ii" or u.unit_id.startswith("vii.ii.")
                         for u in units)


# --------------------------------------------------------------------------- 3.1

def test_rule_removals_emit_none_of_the_removed_units(fathers):
    """Building with the registry emits no work rules A to C remove (3.1): no removed
    document, and no passage an open `passage` entry retires."""
    reg = registry.current()
    removed = registry.removed_document_ids(reg)
    retired = {e["passage_id"] for e in registry.open_removals(reg) if e["scope"] == "passage"}
    assert not [d.title for d in fathers if d.id in removed]
    assert not [(d.title, p.anchor) for d in fathers for p in d.passages
                if registry.resolve_passage_id(d.id, p.anchor, reg) in retired]
    authors = {d.author for d in fathers}
    assert not authors & {"Origen", "Novatian", "Tatian", "Arnobius",
                          "Alexander of Lycopolis"}
    # Of the Apostolic Constitutions, only Book VIII's canons stay (rule D).
    assert [d.id[:8] for d in fathers
            if d.author == "Constitutions of the Holy Apostles"] == ["10d8d7c6"]
    assert {"To His Wife", "On the Apparel of Women"} <= {
        d.title for d in fathers if d.author == "Tertullian"}


def test_book_viii_emits_only_its_canons(fathers):
    d = next(d for d in fathers if d.id.startswith("10d8d7c6"))
    assert {p.chapter_key for p in d.passages} == {"ix.ix.vi"}
    # 3.2 makes the canons a work of their own, "The Apostolic Canons", labelled "Canons".
    assert d.passages[0].chapter_label == "Canons"
    assert {p.work_key for p in d.passages} == {"ix.ix.vi"}
    assert [w.title for w in d.works] == ["The Apostolic Canons"]
    assert len(d.passages) == 6 and [p.position for p in d.passages] == list(range(6))


def test_treatises_attributed_to_cyprian_keep_ii_and_iv(fathers):
    d = _doc(fathers, "third-century-2.xml#iv.vii")
    assert [k for k in dict.fromkeys(p.work_key for p in d.passages)] == \
        ["iv.vii.iii", "iv.vii.v"]


def test_no_novatian_passage_is_built(fathers):
    """3.1's acceptance check: no passage is credited to Novatian or sits in a work by him,
    Epistles XXV, XXIX and XXX included."""
    assert not [d.title for d in fathers if "Novatian" == d.author]
    letters = _doc(fathers, "third-century-2.xml#iv.iv")
    assert not [p.anchor for p in letters.passages
                if p.work_key in ("iv.iv.xxv", "iv.iv.xxix", "iv.iv.xxx")]
    assert [p for p in letters.passages if p.work_key == "iv.iv.lxxiv"]   # Firmilian stays


def test_hippolytus_keeps_his_datable_works(fathers):
    d = _doc(fathers, "third-century-2.xml#iii.iv")
    assert [k for k in dict.fromkeys(p.work_key for p in d.passages)] == \
        ["iii.iv.i.x", "iii.iv.ii.i"]
    assert not [x for x in fathers if x.title == "The Refutation of All Heresies"]


# ------------------------------------------------------------------ 5.6a: Basil (NPNF2-08)

_BASIL = {"npnf208.xml#vii": ("On the Holy Spirit", 30),
          "npnf208.xml#viii": ("The Hexaemeron", 9),
          "npnf208.xml#ix": ("Letters", None)}


@pytest.fixture(scope="module")
def basil():
    return {d.metadata["source_key"].split("/", 1)[1]: d
            for d in build_documents(os.path.join(_SRC, "npnf208.xml"))}


def test_basil_volume_builds_its_three_works(basil):
    assert set(basil) == set(_BASIL)
    for key, (title, chapters) in _BASIL.items():
        d = basil[key]
        assert (d.title, d.author) == (title, "Basil")
        if chapters:
            assert len({p.chapter_key for p in d.passages}) == chapters


def test_basil_head_lines_go_to_the_label(basil):
    for d in basil.values():
        for p in d.passages:
            for para in p.content.split("\n\n"):
                assert not cf._NPNF_NUMBER.match(para), (p.anchor, para)
                assert not cf._CANONICA.match(para), (p.anchor, para)
    sp = basil["npnf208.xml#vii"]
    # The div's title attribute is garbled here; the label reads the printed line.
    label = next(p.chapter_label for p in sp.passages if p.chapter_key == "vii.vi")
    assert label.startswith("Chapter V. That “through whom” is said also")
    letters = basil["npnf208.xml#ix"]
    first = next(p for p in letters.passages if p.chapter_key == "ix.clxxxix")
    assert first.chapter_label == "Letter CLXXXVIII · To Amphilochius, concerning the Canons"
    assert first.content.startswith("“Even a fool,”")


def test_basil_summaries_and_notes_are_not_built(basil):
    built = {p.chapter_key for p in basil["npnf208.xml#ix"].passages}
    skipped = next(w for w in cf.NPNF_WORKS["npnf208.xml"] if w.letters).skip
    assert not built & skipped
    for p in basil["npnf208.xml#ix"].passages:
        assert not any(para.startswith("[") and para.endswith("]") and len(para) < 200
                       for para in p.content.split("\n\n")), p.anchor


def test_basil_letter_197_second_section_is_its_own_work(basil):
    letters = basil["npnf208.xml#ix"]
    part = [p for p in letters.passages if p.chapter_key == "ix.cxcviii/2"]
    assert part and part[0].content.startswith("2. By your earnestness")
    assert all(p.work_key == "ix.cxcviii/2" for p in part)
    head = [p for p in letters.passages if p.chapter_key == "ix.cxcviii"]
    assert head and not any("Dionysius" in p.content for p in head)
    assert {w.work_key for w in letters.works} >= {"ix.cxcviii", "ix.cxcviii/2"}


def test_basil_letter_125_loses_only_its_greek_creed(basil):
    text = "\n\n".join(p.content for p in basil["npnf208.xml#ix"].passages
                      if p.chapter_key == "ix.cxxvi")
    assert "πιστεύομεν" not in text
    assert text.startswith("1. Both men") and "3. Here then all points" in text


def test_basil_editor_brackets(basil):
    text = "\n".join(p.content for d in basil.values() for p in d.passages)
    assert "A.V." not in text and "[lxx" not in text
    assert "[the Spirit]" in text                       # supplied by the translator
    letter_2 = next(p.content for p in basil["npnf208.xml#ix"].passages
                    if p.chapter_key == "ix.iii")
    assert "[I recognised your letter" in letter_2      # Newman's bracketed passages


def test_basil_rule_a_letters_are_not_built(fathers):
    from scripts.npnf_registry import EXCLUDED
    letters = _doc(fathers, "npnf208.xml#ix")
    built = {p.chapter_key.split("/")[0] for p in letters.passages}
    assert not built & set(EXCLUDED["npnf208.xml"])
    assert {"ix.ii", "ix.iii", "ix.ccclv"} <= built     # Letters 1, 2; 360 under rule D
    # Letter 8 stays, labelled Evagrius's (Carter, 24 Nov 2026); Letter 167 is Gregory of
    # Nazianzus's Letter 66, kept in his own letters only.
    assert "ix.ix" in built and "ix.clxviii" not in built
    # Basil is a Doctor: limit 2 keeps his own letters to Libanius; Libanius's leave.
    assert "ix.cccxxx" in built and "ix.cccxxxi" not in built
    # The reader lists only the letters the document holds.
    assert {w.work_key for w in letters.works} == {p.work_key for p in letters.passages}


def test_basil_letter_8_is_credited_to_evagrius_and_its_ids_are_retired():
    import json
    from scripts.npnf_registry import RETIRED_IDS
    reg = registry.current()
    assert not {e["id"] for e in reg.removals} & RETIRED_IDS
    entry = next(w for w in json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "registry", "works.json")))
        if w["work_id"] == "church-fathers/npnf208/ix")
    work = next(x for x in entry["works"] if x["work_key"] == "ix.ix")
    assert work["author"] == "Evagrius Ponticus"
    assert "Second Council of Nicaea" in work["attribution_note"]


def test_basil_letter_from_antipater_is_credited_to_him(basil):
    work = next(w for w in basil["npnf208.xml#ix"].works if w.work_key == "ix.clxxxviii")
    assert work.author == "Antipater"


def test_basil_newman_letters_name_both_translators(fathers):
    import card_notes
    letters = _doc(fathers, "npnf208.xml#ix")
    done = card_notes.apply(letters, {"card_translator": "Translated by Blomfield Jackson (1895)"})
    by_anchor = {p.anchor: (p.metadata or {}).get("translator") for p in done.passages}
    assert by_anchor["ix.xv"] == card_notes.NEWMAN_AND_JACKSON       # Letter 14
    assert by_anchor["ix.iii/from-p17"] == card_notes.NEWMAN_AND_JACKSON
    assert by_anchor["ix.iii/from-p25"] is None      # Letter 2 after Newman's version ends
    assert by_anchor["ix.iv"] is None                                # Letter 3: Jackson's
    assert {k for _, k in card_notes.PASSAGE_TRANSLATORS} <= set(by_anchor)


def test_npnf_registry_lifting_an_exclusion_restores_the_letter(monkeypatch):
    from scripts import npnf_registry
    npnf_registry_excluded = npnf_registry.EXCLUDED
    excluded = {f: dict(divs) for f, divs in npnf_registry.EXCLUDED.items()}
    del excluded["npnf208.xml"]["ix.xl"]
    monkeypatch.setattr(npnf_registry, "EXCLUDED", excluded)
    staged, _, _, problems = npnf_registry.plan(registry.current(), "2026-11-24")
    assert problems == []
    # A second run keeps the closed record.
    staged, _, _, problems = npnf_registry.plan(staged, "2026-11-25")
    assert problems == []
    closed = [e for e in staged.removals if e.get("closed_by") == "5.6a"]
    assert {e["anchor"].split("/")[0] for e in closed} == {"ix.xl"}
    ids = {e["passage_id"] for e in closed}
    assert {r["status"] for r in staged.passages if r["passage_id"] in ids} == {"active"}
    # Excluded again: a new entry under a new ID, and the closed one kept as it was.
    monkeypatch.setattr(npnf_registry, "EXCLUDED", npnf_registry_excluded)
    again, _, _, problems = npnf_registry.plan(staged, "2026-11-26")
    assert problems == []
    assert {e["id"] for e in again.removals if e.get("closed_by")} >= {e["id"] for e in closed}
    reopened = [e for e in again.removals if e["passage_id"] in ids and not e.get("closed_by")]
    assert reopened and not {e["id"] for e in reopened} & {e["id"] for e in closed}


def test_basil_rule_a_removals_cover_every_excluded_passage(basil):
    from scripts.npnf_registry import EXCLUDED
    letters = basil["npnf208.xml#ix"]
    reg = registry.current()
    entries = {e["passage_id"]: e for e in reg.removals
               if e["document_id"] == letters.id and e["scope"] == "passage"}
    for p in letters.passages:
        if p.chapter_key.split("/")[0] in EXCLUDED["npnf208.xml"]:
            pid = reg.row_by_anchor[(letters.id, p.anchor)]["passage_id"]
            assert entries[pid]["reason"] == EXCLUDED["npnf208.xml"][
                p.chapter_key.split("/")[0]][0], p.anchor
            assert 11501 <= int(entries[pid]["id"].split("-")[1]) <= 11999


def test_basil_letter_labels_name_built_letters(basil):
    from attributions import BASIL_LETTER_LABELS
    keys = {w.work_key for w in basil["npnf208.xml#ix"].works}
    assert set(BASIL_LETTER_LABELS) <= keys


def test_basil_judgments_quote_their_notes():
    from ingest.common import _strip_tags
    from scripts.npnf_registry import JUDGMENTS
    from xml.etree.ElementTree import tostring
    def flat(t):
        return " ".join(t.replace("’", "'").replace("“", '"').replace("”", '"').split())

    for work_id, rows in JUDGMENTS.items():
        file = work_id.split("/")[1] + ".xml"            # church-fathers/npnf208/ix
        root = cf._read_root(os.path.join(_SRC, file))
        divs = {e.get("id"): e for e in root.iter() if e.get("id")}
        for element, quote, _, _ in rows:
            assert flat(quote) in flat(_strip_tags(tostring(divs[element], encoding="unicode")))


# ------------------------------------------------------------------ 5.6a: NPNF2-07

@pytest.fixture(scope="module")
def npnf207():
    return {d.metadata["source_key"].split("#")[1]: d
            for d in build_documents(os.path.join(_SRC, "npnf207.xml"))}


def test_npnf207_builds_cyril_and_gregorys_works(npnf207):
    assert {k: (d.title, d.author) for k, d in npnf207.items()} == {
        "ii": ("Catechetical Lectures", "Cyril of Jerusalem"),
        "iii": ("Select Orations", "Gregory of Nazianzus"),
        "iv": ("Select Letters", "Gregory of Nazianzus")}
    assert len({p.chapter_key for p in npnf207["ii"].passages}) == 24
    assert len({p.chapter_key for p in npnf207["iii"].passages}) == 24
    assert [w.title for w in npnf207["ii"].works] == [
        "Lectures to the Candidates for Baptism", "Mystagogical Lectures"]


def test_cyril_reading_is_an_epigraph_and_his_headings_are_marked(npnf207):
    cyril = npnf207["ii"]
    first = next(p for p in cyril.passages if p.chapter_key == "ii.vi")
    assert first.chapter_label.startswith("Lecture II. On Repentance")
    marks = first.metadata["headings"]
    assert [m["role"] for m in marks[:2]] == ["epigraph", "epigraph"]
    assert first.content.startswith("Ezekiel xviii. 20–23")
    inner = [(m, p) for p in cyril.passages if p.chapter_key == "ii.viii"
             for m in (p.metadata or {}).get("headings", []) if m["role"] == "heading"]
    assert len(inner) == 16 and all(m["level"] == 2 for m, _ in inner)
    assert any(p.content[m["at"]:m["end"]] == "I. Of God." for m, p in inner)


def test_npnf207_editors_matter_is_cut(npnf207):
    text = "\n".join(p.content for d in npnf207.values() for p in d.passages)
    for editor in ("It is generally agreed that this oration",      # Oration II's intro
                   "Appendix to Lecture IX",                           # Gifford's variants
                   "The Oration is thus analysed by Abbe Benoît",
                   "(Perhaps about a.d. 357 or 358",                   # a letter's dating
                   "(We insert here the three letters",
                   "Division III.", "Gregory Nazianzen.\n"):
        assert editor not in text, editor
    assert "(To the Reader.)" in text          # the manuscripts' note, kept


def test_gregory_letters_are_numbered_works(npnf207):
    letters = npnf207["iv"]
    titles = {w.work_key: w.title for w in letters.works}
    assert titles["iv.ii.iii"] == "Letter CI"
    assert titles["iv.iv.ii.i"] == "Letter XI"          # printed "Ep. I."
    assert len(set(titles.values())) == len(titles)
    text = "\n".join(p.content for p in letters.passages)
    assert "Od. viii. 492" not in text
    label = next(p.chapter_label for p in letters.passages if p.chapter_key == "iv.iii.ii")
    assert label == "Letter II · To Basil"
    # The editor's pointers to letters printed above are not built.
    assert not {"iv.iv.iii.i", "iv.iv.vi.vi", "iv.iv.ix.iv"} & {
        p.chapter_key for p in letters.passages}


def test_mystagogical_lectures_do_not_take_the_lectures_date():
    import json
    entry = next(w for w in json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "registry", "works.json")))
        if w["work_id"] == "church-fathers/npnf207/ii")
    assert entry["date_display"] == "347 or 348"
    work = next(x for x in entry["works"] if x["work_key"] == "ii.xxiii")
    assert work["date_display"] == "date disputed" and work["certainty"] == "disputed"


# ------------------------------------------------------------------ 5.6a: NPNF2-12, NPNF2-13

@pytest.fixture(scope="module")
def leo_gregory():
    return {(f, d.metadata["source_key"].split("#")[1]): d
            for f in ("npnf212.xml", "npnf213.xml")
            for d in build_documents(os.path.join(_SRC, f))}


def test_npnf212_and_213_build_leo_and_gregorys_works(leo_gregory):
    assert {k: (d.title, d.author) for k, d in leo_gregory.items()} == {
        ("npnf212.xml", "ii.iv"): ("Letters of Leo the Great", "Leo the Great"),
        ("npnf212.xml", "ii.v"): ("Sermons", "Leo the Great"),
        ("npnf212.xml", "iii.iv"): ("The Book of Pastoral Rule", "Gregory the Great"),
        ("npnf212.xml", "iii.v"): ("Register of Letters, Books I to VIII", "Gregory the Great"),
        ("npnf213.xml", "ii"): ("Register of Letters, Books IX to XIV", "Gregory the Great")}
    assert len(leo_gregory[("npnf212.xml", "ii.v")].works) == 48


def test_leo_editors_summaries_are_cut(leo_gregory):
    letters, sermons = (leo_gregory[("npnf212.xml", k)] for k in ("ii.iv", "ii.v"))
    text = "\n".join(p.content for d in (letters, sermons) for p in d.passages)
    for editor in ("Through the negligence of the authorities the Pelagian heresy",
                   "The story of the magi not only a byegone fact",       # a sermon's
                   "Having been elected in absence"):
        assert editor not in text, editor
    built = {p.chapter_key for p in letters.passages}
    # Letters given only as Feltoe's summary are not built: in parentheses, in brackets
    # (the "Second Tome", Letter CLXV), or as a pointer.
    assert not {"ii.iv.ii", "ii.iv.clix", "ii.iv.cliv", "ii.iv.xxx"} & built
    assert "ii.iv.xxxi" in built                     # the letter XXX's note points to
    # Letters LV to LVIII: the summary of four goes; Galla Placidia's LVI stays, hers.
    work = next(w for w in letters.works if w.work_key == "ii.iv.lv")
    assert (work.title, work.author) == ("Letter LVI", "Galla Placidia")
    label = next(p.chapter_label for p in letters.passages if p.chapter_key == "ii.iv.lv")
    assert label == "Letter LVI · From Galla Placidia Augusta to Theodosius"
    by_letter = {}
    for p in letters.passages:
        by_letter[p.chapter_key] = by_letter.get(p.chapter_key, "") + "\n\n" + p.content
    # Leo's salutations stay where the summaries go (Letters XVIII, XXIX, CLIX).
    assert "Leo, bishop of the city of Rome, to Januarius" in by_letter["ii.iv.xviii"]
    assert "Those who renounce heresy and schism" not in by_letter["ii.iv.xviii"]
    assert "To Caesar Theodosius" in by_letter["ii.iv.xxix"]
    assert "(Leo, the bishop, to Nicaetas" in by_letter["ii.iv.cliii"]
    # Letter CIV's "(To Marcian Augustus, about…)" is Feltoe's summary, cut.
    assert by_letter["ii.iv.xcix"].lstrip().startswith("By the great bounty of God")
    # Rusticus's questions stay, marked as headings (Letter CLXVII).
    rusticus = [p for p in letters.passages if p.chapter_key == "ii.iv.clxi"]
    marks = [p.content[m["at"]:m["end"]] for p in rusticus
             for m in (p.metadata or {}).get("headings", [])]
    assert len(marks) == 19 and marks[0].startswith("Question I. Concerning a presbyter")
    labels = {p.chapter_key: p.chapter_label for p in letters.passages}
    assert labels["ii.iv.lii"] == "Letter LII · From Theodoret, Bishop of Cyrus, to Leo"
    assert labels["ii.iv.xxviii"] == "Letter XXVIII · To Flavian commonly called “the Tome”"


def test_pastoral_rule_labels_its_parts(leo_gregory):
    rule = leo_gregory[("npnf212.xml", "iii.iv")]
    labels = list(dict.fromkeys(p.chapter_label for p in rule.passages))
    assert labels[0] == "Part I, Prologue"
    assert labels[1] == "Part I, Chapter I. That the unskilful venture not to approach an " \
                        "office of authority"
    assert any(x.startswith("Part II, Chapter I. How one who has in due order") for x in labels)
    assert labels[-1].startswith("Part IV. How the Preacher")
    # Gregory's letter to John stays; Barmby's preface on the title does not.
    assert rule.passages[0].content.startswith("Gregory to his most reverend")
    assert not any("Liber Regulæ Pastoralis" in p.content for p in rule.passages)


def test_register_letters_carry_their_book(leo_gregory):
    first, second = (leo_gregory[k] for k in (("npnf212.xml", "iii.v"), ("npnf213.xml", "ii")))
    titles = {w.work_key: w.title for w in first.works}
    assert titles["iii.v.ii.i"] == "Book II, Letter III"
    assert len(set(titles.values())) == len(titles)
    text = "\n".join(p.content for p in first.passages)
    assert "Indiction IX., Being the First Year" not in text          # the Book's dating line
    assert "Gregory to Justinus, Praetor of Sicily." in text           # his salutation, kept
    # Register II, 41's second version, from other manuscripts, is a part of its own.
    other = [p for p in first.passages if p.chapter_key == "iii.v.ii.xxii/version"]
    assert other and other[0].content.startswith("Gregory to Castorius, Bishop of Ariminum.")
    assert other[0].chapter_label == "Book II, Letter XLI · To Castorius, Bishop: Second version"
    paper = [p.content[m["at"]:m["end"]] for p in other
             for m in (p.metadata or {}).get("headings", [])]
    assert paper == ["Of the privileges of Monasteries."]
    assert "[In place of the epistle" not in text
    for note in ("[In Colbert. and Paul. diac.", "[Here follows an account",
                 "[The beginning of this epistle is the same", "[See Reg. Past.",
                 "[A long passage, thus beginning"):
        assert note not in text, note                                    # Barmby's brackets
    assert "[i.e. monks of St. Theodore]" in text                       # his gloss stays
    second_text = "\n".join(p.content for p in second.passages)
    assert "[N.B. This date is absent" not in second_text
    assert "(ministerium: in Bede, mysterium)" not in second_text          # his reading
    # Augustine of Canterbury's questions head the Book of Answers (Book XI, 64), level 2.
    marks = [(m, p) for p in second.passages if p.chapter_key == "ii.vii.xxx"
             for m in (p.metadata or {}).get("headings", [])]
    assert marks and all(m["level"] == 2 for m, _ in marks)
    marked = [p.content[m["at"]:m["end"]] for m, p in marks]
    assert {"Augustine’s request.", "The grant of Gregory."} <= set(marked)
    assert sum(x.startswith("Answer of") for x in marked) == 11
    answers = next(p for p in second.passages if p.chapter_key == "ii.vii.xxx")
    assert answers.content.startswith("Preface.—Through my most beloved son")  # incipit cut
    assert "ii.ix.vii" not in {p.chapter_key for p in second.passages}   # a pointer
    senders = {w.work_key: w.author for w in second.works}
    assert senders["ii.v.lx"] == "Columbanus"


def test_leo_and_gregory_registry_labels():
    import json
    works = {w["work_id"]: w for w in json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "registry", "works.json")))}
    register = {x["work_key"]: x for x in works["church-fathers/npnf213/ii"]["works"]}
    assert (register["ii.x.viii"]["author"], register["ii.x.viii"]["certainty"]) == (
        "Pseudo-Gregory the Great", "pseudonymous")
    assert register["ii.v.xxx"]["certainty"] == "disputed"
    assert works["church-fathers/npnf212/iii.iv"]["attribution"]["clavis"] == "CPL 1712"
    # Letters printed only in part carry a note on every row of the letter.
    rows = [json.loads(line) for line in open(os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "registry", "passages", "church-fathers.jsonl"))]
    noted = {r["anchor"].split("/")[0] for r in rows if (r.get("note") or "").startswith(
        ("Only chapter III", "This letter opens as", "Two passages of this letter",
         "Most of this letter", "Parts of this letter"))}
    assert noted == {"ii.iv.xcvi", "iii.v.i.xix", "iii.v.ii.x", "ii.ix.v", "iii.v.i.xviii"}
    from scripts.npnf_registry import EXCLUDED
    assert EXCLUDED["npnf212.xml"]["ii.iv.xxi"][0] == "rule-a"      # Eutyches's letter
    leo = next(d for d in build_all() if d.title == "Letters of Leo the Great")
    assert "ii.iv.xxi" not in {p.chapter_key for p in leo.passages}
