"""The stopgap Catechism contents tree (#255): the generated headings file, and how
/toc points its headings at today's passages."""

import json
from pathlib import Path

import pytest

from app import catechism_contents as module
from app.catechism_contents import catechism_contents
from app.routes.documents import get_document_toc
from tests.pg_cluster import CORPUS_SCHEMA, local_cluster
from tests.test_reader_outline_endpoints import USER, _routes_on


def heading(key, first, last, children=(), kind="heading"):
    return {"key": key, "kind": kind, "label": key, "short_label": key, "first": first,
            "last": last, "range_label": f"§§{first}–{last}", "children": list(children)}


# A part with no paragraphs of its own (it opens where its first article does), two
# articles, and a sub-heading that starts inside the first article's second passage.
HEADINGS = [heading("part", 1, 6, kind="part", children=[
    heading("a1", 1, 4, kind="article", children=[heading("a1/ii", 3, 4)]),
    heading("a2", 5, 6, kind="article"),
])]
PASSAGES = [("c1", "ccc/1", [1, 2]), ("c1", "ccc/3", [3, 4]),
            ("c2", "ccc/5", [5]), ("c2", "ccc/5b", [5]), ("c2", "ccc/6", [6])]


def _shape(nodes):
    return [(n.key, n.chapter_key, n.anchor, n.range_label, _shape(n.children)) for n in nodes]


def test_headings_open_the_first_passage_holding_their_first_paragraph():
    tree = catechism_contents(PASSAGES, ["c1", "c2"], HEADINGS)
    assert _shape(tree) == [("part", "c1", "ccc/1", "§§1–6", [
        ("a1", "c1", "ccc/1", "§§1–4", [("a1/ii", "c1", "ccc/3", "§§3–4", [])]),
        ("a2", "c2", "ccc/5", "§§5–6", []),   # the first of the two passages holding §5
    ])]


def test_a_paragraph_no_passage_holds_withholds_the_tree():
    assert catechism_contents(PASSAGES[:2], ["c1"], HEADINGS) is None


def test_chapters_out_of_reading_order_withhold_the_tree():
    assert catechism_contents(PASSAGES, ["c2", "c1"], HEADINGS) is None


def test_passages_out_of_order_within_a_chapter_withhold_the_tree():
    # Both sub-headings sit in c1, so only passage order can catch the swap.
    swapped = [("c1", "ccc/3", [3, 4]), ("c1", "ccc/1", [1, 2]),
               ("c2", "ccc/5", [5]), ("c2", "ccc/6", [6])]
    assert catechism_contents(swapped, ["c1", "c2"], HEADINGS) is None


@pytest.mark.parametrize("bad", [[None], ["12a"], [[1]]])
def test_malformed_paragraph_lists_withhold_the_tree_rather_than_fail(bad):
    assert catechism_contents([("c1", "ccc/1", bad), *PASSAGES], ["c1", "c2"], HEADINGS) is None


def test_a_passage_whose_chapter_is_not_listed_withholds_the_tree():
    assert catechism_contents(PASSAGES, ["c1"], HEADINGS) is None


# ── The generated file ────────────────────────────────────────────────────────

GENERATED = json.loads(Path(module.__file__).with_name("catechism_contents.json").read_text())


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node["children"])


def test_generated_roots_are_the_prologue_and_four_parts():
    assert [n["short_label"] for n in GENERATED] == [
        "Prologue", "Part One · The Profession of Faith",
        "Part Two · The Celebration of the Christian Mystery", "Part Three · Life in Christ",
        "Part Four · Christian Prayer"]
    assert GENERATED[0]["first"] == 1 and GENERATED[-1]["last"] == 2865


def test_generated_headings_are_in_order_with_unique_keys_and_no_capitals():
    nodes = list(_walk(GENERATED))
    starts = [n["first"] for n in nodes]
    assert starts == sorted(starts)
    assert len({n["key"] for n in nodes}) == len(nodes)
    for node in nodes:
        words = node["short_label"].replace("·", " ").split()
        shouting = [w for w in words if len(w.strip('"?,.:')) > 1 and w.isupper()
                    and not set(w.strip('".')) <= set("IVXL")]
        assert not shouting, node["short_label"]


def test_generated_penance_holds_indulgences():
    penance = next(n for n in _walk(GENERATED)
                   if n["short_label"] == "Article 4 · The Sacrament of Penance and Reconciliation")
    assert (penance["first"], penance["last"], penance["range_label"]) == (1422, 1498, "§§1422–1498")
    indulgences = next(c for c in penance["children"] if c["label"] == "X. Indulgences")
    assert indulgences["first"] <= 1471 <= indulgences["last"]
    assert penance["children"][-1]["label"] == "In Brief"


def test_generated_restores_section_two_and_its_creeds_heading():
    section = GENERATED[1]["children"][1]
    assert section["short_label"] == "Section Two · The Profession of the Christian Faith"
    assert section["children"][0]["short_label"] == "I. The Creeds"
    assert section["children"][0]["range_label"] == "§§185–197"


# ── /toc ──────────────────────────────────────────────────────────────────────

CCC = "00000000-0000-0000-0000-0000000000cc"
SEED = f"""
    INSERT INTO documents (id, collection, title, translation, metadata)
    VALUES ('{CCC}', 'catechism', 'Catechism', '', '{{}}');
    INSERT INTO chunks (document_id, position, content, anchor, chapter_key, chapter_label, metadata)
    VALUES
        ('{CCC}', 0, 'a', 'ccc/1', 'c1', 'CCC §§1–4', '{{"ccc_paragraphs": [1, 2]}}'),
        ('{CCC}', 1, 'b', 'ccc/3', 'c1', 'CCC §§1–4', '{{"ccc_paragraphs": [3, 4]}}'),
        ('{CCC}', 2, 'c', 'ccc/5', 'c2', 'CCC §§5–6', '{{"ccc_paragraphs": [5, 6]}}');
"""


@pytest.fixture()
async def db():
    with local_cluster("tc-catechism-") as cluster:
        cluster.sql(CORPUS_SCHEMA)
        # The shared test schema leaves out chunks.metadata, which this tree reads.
        cluster.sql("ALTER TABLE chunks ADD COLUMN metadata jsonb")
        cluster.migrate("0037_document_outline.sql", "0040_document_contents.sql")
        cluster.sql(SEED)
        cluster.sql(f"SELECT refresh_document_outline('{CCC}')")
        async with _routes_on(cluster):
            yield cluster


async def test_toc_serves_the_catechism_tree_when_none_is_stored(db, monkeypatch):
    monkeypatch.setattr(module, "_headings", lambda: HEADINGS)

    toc = await get_document_toc(CCC, user=USER)

    assert [c.chapter_key for c in toc.chapters] == ["c1", "c2"]
    assert _shape(toc.contents) == [("part", "c1", "ccc/1", "§§1–6", [
        ("a1", "c1", "ccc/1", "§§1–4", [("a1/ii", "c1", "ccc/3", "§§3–4", [])]),
        ("a2", "c2", "ccc/5", "§§5–6", []),
    ])]


async def test_a_stored_catechism_tree_replaces_the_stopgap(db, monkeypatch):
    monkeypatch.setattr(module, "_headings", lambda: HEADINGS)
    db.sql(f"""
        INSERT INTO document_contents
            (document_id, ordinal, parent_ordinal, depth, node_key, kind, label, short_label,
             chapter_key, anchor, range_label)
        VALUES ('{CCC}', 1, NULL, 0, 'stored', 'part', 'Stored', 'Stored', 'c1', NULL, NULL);
    """)

    toc = await get_document_toc(CCC, user=USER)

    assert [n.key for n in toc.contents] == ["stored"]


def test_generated_headings_with_sub_headings_only_group_them():
    # Each starts where its first child does, so the reader expands it rather than
    # opening it, and every place to open is a leaf (a heading's own opening paragraphs
    # are an "Introduction" entry).
    for node in _walk(GENERATED):
        if node["children"]:
            assert node["first"] == node["children"][0]["first"], node["short_label"]
