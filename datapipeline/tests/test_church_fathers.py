import os
import re
from collections import defaultdict

import pytest

import registry
from checks import source_text
from ingest import church_fathers as cf
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
    # 128 since 1.8c parses his text and brings the document back.
    assert len(docs) == 128
    for doc in docs:
        groups = defaultdict(list)
        for passage in doc.passages:
            assert _cut_length(passage.content) <= 4_000
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


def test_ignatius_letters_open_with_salutation(fathers):
    # The 15 Ignatian letters that print a greeting above their first chapter; the
    # short letters to John and Mary carry theirs as the title, the Martyrdom has none.
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


def test_panegyric_labels(fathers):
    d = _doc(fathers, "third-century-3.xml#iii.iii")
    panegyric = [p for p in d.passages if p.chapter_key.startswith("iii.iii.iv.")]
    assert panegyric
    assert not [p.chapter_label for p in d.passages if "Argument" in p.chapter_label]


def test_cyprian_letters_credited_to_senders(fathers):
    d = _doc(fathers, "third-century-2.xml#iv.iv")
    works = {w.work_key: w for w in d.works}
    for div, (sender, _) in cf._LETTER_SENDERS.items():
        pieces = [p for p in d.passages if p.work_key == div]
        assert pieces, div
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
