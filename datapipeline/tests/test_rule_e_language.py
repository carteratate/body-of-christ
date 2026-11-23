"""Non-English passages (corpus-cleanup 3.3): the approved removals, the Latin paragraphs
cut from English passages, the omission note, and the release check `english_only`."""
import sys, os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from dataclasses import replace

import pytest

from checks import language
from checks.language import english_only, foreign_runs, latin_runs, run_sha1
from ingest import church_fathers as cf
from ingest.editorial import span_sha1
from model import Document, Passage
from registry import WorkRegistry, load_registry, resolve_passage_id, validate
from scripts import language_removals as lr

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources")
_vendored = all(os.path.isdir(os.path.join(_SRC, c)) for c in ("church-fathers", "encyclicals"))
vendored = pytest.mark.skipif(not _vendored, reason="sources not vendored")

TOMBSTONE = "No public-domain English translation is available."
EMPTY = WorkRegistry([], [], [], [], [])


@pytest.fixture(scope="module")
def reg():
    return load_registry()


def _mine(reg):
    return [e for e in reg.removals if e.get("added_by") == "3.3"]


# ── The registry entries ────────────────────────────────────────────────────

def test_registry_is_valid(reg):
    assert validate(reg) == []


def test_exactly_the_approved_entries(reg):
    mine = _mine(reg)
    assert all(e["reason"] == "translation-in-preparation" for e in mine)
    assert sorted(int(e["id"][3:]) for e in mine) == list(range(4001, 4001 + len(mine)))
    docs = [e for e in mine if e["scope"] == "document"]
    assert [(e["document_id"], e["tombstone"]) for e in docs] == [(lr.UBI_LUTETIAM, TOMBSTONE)]
    passages = [e for e in mine if e["scope"] == "passage"]
    assert all(e["tombstone"] == TOMBSTONE for e in passages)
    rows = {r["passage_id"]: r for r in reg.passages}
    approved = {(d, resolve_passage_id(d, a, reg)) for d, anchors, _ in lr.PASSAGES
                for a in anchors}
    # The approved anchors, plus the two live pieces 1.10b and 1.10c redirected into them.
    assert approved <= {(e["document_id"], e["passage_id"]) for e in passages}
    assert len(passages) == len(approved) + 2
    for e in passages:
        assert rows[e["passage_id"]]["status"] == "retired"
        assert rows[e["passage_id"]]["live_anchor"] == e["anchor"]
    spans = [e for e in mine if e["scope"] == "span"]
    assert {(e["document_id"], e["anchor"], e["span"]["sha1"]) for e in spans} == {
        (d, a, s) for (d, a), shas in cf.NON_ENGLISH_PARAGRAPHS.items() for s in shas}


def test_the_redirects_into_retired_pieces_are_closed(reg):
    retired = {e["passage_id"] for e in _mine(reg) if e["scope"] == "passage"}
    for r in reg.redirects:
        if r["new_passage_id"] in retired or r["old_passage_id"] in retired:
            assert r.get("closed_by") == "3.3", r


def test_no_entry_holds_the_original_text(reg):
    for e in _mine(reg):
        assert latin_runs(json.dumps(e)) == [], e["id"]


def test_rerun_changes_nothing(reg):
    copy = WorkRegistry(*(json.loads(json.dumps(x)) for x in (
        reg.works, reg.passages, reg.redirects, reg.removals, reg.kept_text)))
    entries = lr.plan(copy, "2026-11-14")
    dates = {e["id"]: e["added_on"] for e in _mine(reg)}
    for e in entries:
        e["added_on"] = dates[e["id"]]
    lr.apply(copy, entries, "2026-11-14")
    assert copy.removals == reg.removals
    assert copy.passages == reg.passages
    assert copy.redirects == reg.redirects


def test_works_that_keep_passages_are_the_noted_ones(reg):
    losing = {e["document_id"] for e in _mine(reg) if e["scope"] in ("passage", "span")}
    assert losing == set(cf.NON_ENGLISH_OMITTED)


# ── Cutting a Latin paragraph ───────────────────────────────────────────────

def _passage(content, units=()):
    return Passage(content=content, reference="r", anchor="a", chapter_key="c",
                   chapter_label="C", position=0, source_units=units)


def test_cut_paragraph_moves_offsets_and_drops_units_inside_it():
    latin, english = "Tempus autem opportunum.", "Well, I also agree."
    p = _passage(f"{latin}\n\n{english}", (("p3", 0), ("p7", len(latin) + 2)))
    out = cf._without_paragraphs(p, frozenset({span_sha1(latin)}))
    assert out.content == english
    assert out.source_units == (("p7", 0),)
    tail = _passage(f"{english}\n\n{latin}", (("p30", 0), ("p36", len(english) + 2)))
    out = cf._without_paragraphs(tail, frozenset({span_sha1(latin)}))
    assert (out.content, out.source_units) == (english, (("p30", 0),))


def test_unit_offsets_measured_before_cleaning_go_to_the_nearest_paragraph():
    # The adapter's offsets land a few characters from the paragraph they open.
    latin, english = "Tempus autem opportunum conjunctionis solis.", "Well, I also agree."
    p = _passage(f"{latin}\n\n{english}", (("p3", 0), ("p7", len(latin) - 5)))
    assert cf._without_paragraphs(p, frozenset({span_sha1(latin)})).source_units == \
        (("p7", 0),)
    tail = _passage(f"{english}\n\n{latin}", (("p30", 0), ("p36", len(english) + 1)))
    assert cf._without_paragraphs(tail, frozenset({span_sha1(latin)})).source_units == \
        (("p30", 0),)


def test_cut_paragraph_takes_its_footnotes_and_moves_the_rest():
    latin, english = "Tempus autem opportunum.", "Well, I also agree."
    content = f"{latin}\n\n{english}"
    notes = [{"n": 1, "text": "Gen. i. 27.", "at": len(latin)},
             {"n": 2, "text": "Deut. xiv. 7.", "at": len(content)}]
    p = replace(_passage(content), metadata={"book": "II", "footnotes": notes})
    out = cf._without_paragraphs(p, frozenset({span_sha1(latin)}))
    assert out.metadata == {"book": "II", "footnotes": [
        {"n": 1, "text": "Deut. xiv. 7.", "at": len(english)}]}
    only = replace(p, metadata={"footnotes": notes[:1]})
    assert cf._without_paragraphs(only, frozenset({span_sha1(latin)})).metadata == {}


def test_a_paragraph_not_found_fails_the_build():
    with pytest.raises(ValueError, match="not found"):
        cf._without_paragraphs(_passage("English only."), frozenset({"0" * 40}))


@vendored
@pytest.mark.sources
def test_build_cuts_the_latin_and_notes_the_works():
    docs = {d.id: d for d in cf.build_all()}
    for (doc, anchor), shas in cf.NON_ENGLISH_PARAGRAPHS.items():
        p = next(p for p in docs[doc].passages if p.anchor == anchor)
        assert latin_runs(p.content) == [] and p.content
        assert not {span_sha1(x) for x in p.content.split("\n\n")} & shas
    for doc in cf.NON_ENGLISH_OMITTED:
        assert docs[doc].notes == cf.NON_ENGLISH_NOTE


# ── The check ───────────────────────────────────────────────────────────────

def test_runs_by_language():
    assert [l for l, _ in foreign_runs("Ac Valentiniani quidem, qui desuper ex divinis "
                                       "emissionibus deduxere conjugationes, acceptum")] == ["la"]
    assert [l for l, _ in foreign_runs("Io dico che, pensando al suo valore amor si dolce "
                                       "si mi si fa sentire")] == ["it"]
    assert [l for l, _ in foreign_runs("C'est la confiance et rien que la confiance qui "
                                       "doit nous conduire")] == ["fr"]


def test_cited_titles_and_terms_of_art_are_english():
    assert foreign_runs('Augustine says (De Nup. et Concup. i): "marriage is good"') == []
    assert foreign_runs("as the Philosopher says (De Somn. et Vigil. ii), sleep is") == []
    assert foreign_runs("acting per se vel per alium in this matter") == []
    assert foreign_runs("Lo, again confusion; lo, again grief") == []
    assert latin_runs("a marriage ratum et non consummatum can be dissolved") == []


def test_mostly_foreign_is_an_untranslated_paragraph_not_a_quotation():
    assert language.mostly_foreign(LATIN)
    assert language.mostly_foreign("Et rursus:—")
    assert not language.mostly_foreign(
        "As Saint Augustine put it: nemo autem illam carnem manducat, nisi prius adoraverit; "
        "no one eats that flesh without first adoring it, and we should sin were we not to "
        "adore it, as the Church has always taught in her liturgy and her prayer.")
    assert not language.mostly_foreign("")


def test_withheld_chapters_are_those_retired_whole():
    from checks.source_text import withheld_chapters
    assert withheld_chapters() == {("second-century.xml", "vi.iv.iii"),
                                   ("third-fourth-century.xml", "iii.ii.vi.xxiii"),
                                   ("third-fourth-century.xml", "iii.iv.xii")}


def _doc(*passages, doc_id="d1"):
    return Document(id=doc_id, collection="church-fathers", title="T",
                    passages=[replace(_passage(c), anchor=f"a{i}", position=i)
                              for i, c in enumerate(passages)])


LATIN = "Venio nunc ad eam, quae percipitur ex tactu, voluptatem: qui sensus est quidem totius"


def test_english_only_fails_an_unapproved_run_and_a_language():
    d = _doc("Plain English text about the Church.", LATIN)
    failures = english_only([d], EMPTY, approved=set())
    assert [(p.anchor, detail.split(" run")[0]) for _, p, detail in failures] == [("a1", "la")]
    run = foreign_runs(LATIN)[0][1]
    assert english_only([d], EMPTY, approved={("d1", "a1", run_sha1(run))}) == []
    d.passages[0] = replace(d.passages[0], language="la")
    assert [p.anchor for _, p, _ in english_only([d], EMPTY, approved=set())] == ["a0", "a1"]


def test_english_only_skips_what_the_registry_retires():
    d = _doc(LATIN)
    removal = {"id": "rm-1", "scope": "document", "document_id": "d1", "anchor": None}
    assert english_only([d], WorkRegistry([], [], [], [removal], []), approved=set()) == []


def test_approved_file_is_sorted_and_holds_no_long_text():
    with open(language.APPROVED_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    keys = [(r["document_id"], r["anchor"], r["sha1"]) for r in rows]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert all(len(r["starts"].split()) <= 6 for r in rows)


@vendored
@pytest.mark.sources
def test_the_build_is_english():
    from publication import SOURCE_BUILDS
    docs = [d for c in ("church-fathers", "encyclicals") for d in SOURCE_BUILDS[c]()]
    assert [(d.title, p.anchor, x) for d, p, x in english_only(docs)] == []
