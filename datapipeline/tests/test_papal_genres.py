"""1.3b: every papal document has a genre (its kind) and, where recorded, a form (bull or
brief), cited in the tracked papal_genres.csv and copied into the vendored manifests."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest

import papal_genres
import vendor_sources
from registry.genres import OTHER, PAPAL_FORMS, PAPAL_GENRES

_SOURCES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources")
_vendored = all(os.path.exists(os.path.join(_SOURCES, c, "manifest.json"))
                for c in papal_genres.COLLECTIONS)
_LISTS = {"encyclicals": vendor_sources.ENCYCLICALS,
          "apostolic-exhortations": vendor_sources.APOSTOLIC_EXHORTATIONS,
          "papal-documents": vendor_sources.PAPAL_DOCUMENTS}


def _listed_slugs(collection):
    """The slugs vendor_sources gives its list, the later of two equal titles taking -year."""
    seen = []
    for title, _author, year, _url in _LISTS[collection]:
        base = vendor_sources._slug(title)
        seen.append(base if base not in seen else f"{base}-{year}")
    return seen


def test_the_table_is_sound():
    assert papal_genres.problems() == []


def test_values_come_from_the_genre_module():
    assert papal_genres.GENRES == PAPAL_GENRES + (OTHER,)
    labels = papal_genres.load().values()
    assert {x.genre for x in labels} <= set(PAPAL_GENRES + (OTHER,))
    assert {x.form for x in labels} <= set(PAPAL_FORMS) | {None}


def test_every_listed_document_has_a_row_in_its_collection():
    """Every vendored document, and every one a printing gives alone (5.9)."""
    from ingest import papal_printings

    labels = papal_genres.load()
    listed = {(c, s) for c in papal_genres.COLLECTIONS for s in _listed_slugs(c)} | {
        tuple(p.key.split("/", 1)) for c in papal_genres.COLLECTIONS
        for p in papal_printings.printed_only(c)}
    assert {(x.collection, slug) for slug, x in labels.items()} == listed


def test_a_bad_row_is_refused(tmp_path):
    path = tmp_path / "papal_genres.csv"
    path.write_text(",".join(papal_genres.COLUMNS) + "\n"
                    "a,encyclicals,bull,,https://example.org,its heading\n"
                    "b,encyclicals,encyclical,breve,https://example.org,its heading\n"
                    "c,encyclicals,encyclical,,,\n", encoding="utf-8")
    bad = papal_genres.problems(str(path))
    assert any("a: genre 'bull'" in m for m in bad)
    assert any("b: form 'breve'" in m for m in bad)
    assert any("c: no evidence URL" in m for m in bad) and any("c: no evidence" == m for m in bad)
    with pytest.raises(ValueError):
        papal_genres.load(str(path))


def test_disagreement_follows_the_collection_name():
    assert not papal_genres.disagrees("encyclicals", "encyclical")
    assert papal_genres.disagrees("encyclicals", "apostolic-exhortation")
    assert not papal_genres.disagrees("papal-documents", "apostolic-letter")
    assert papal_genres.disagrees("papal-documents", "encyclical")


@pytest.mark.skipif(not _vendored, reason="vendored papal manifests not present")
def test_every_papal_manifest_entry_has_genre():
    labels = papal_genres.load()
    for collection in papal_genres.COLLECTIONS:
        with open(os.path.join(_SOURCES, collection, "manifest.json"), encoding="utf-8") as f:
            for e in json.load(f):
                where = f"{collection}/{e['slug']}"
                assert e.get("genre") in PAPAL_GENRES + (OTHER,), where
                assert e.get("form") in PAPAL_FORMS + (None,), where
                x = labels[e["slug"]]
                assert (x.collection, x.genre, x.form) == (collection, e["genre"], e.get("form")), where


@pytest.mark.skipif(not _vendored, reason="vendored papal manifests not present")
def test_vendored_counts_and_disagreements(capsys):
    text = papal_genres.report(_SOURCES)
    with capsys.disabled():
        print("\n" + text)
    assert "Genre disagrees with collection" in text
