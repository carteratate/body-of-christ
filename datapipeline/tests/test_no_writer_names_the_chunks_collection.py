"""No datapipeline code outside the tests may name the `chunks` Qdrant collection.

Everything that writes Qdrant takes its collection from a publish (`chunks-<release>`)
or from QDRANT_WRITE_COLLECTION, which has no default, so a run can never fall back to
the collection users search. `"chunks"` is also the Postgres table, so this reads the
syntax tree: the table's name is allowed only in the modules that write SQL by table
name, and nowhere that takes a Qdrant collection.
"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SKIPPED_DIRS = {"tests", ".venv", "sources", "releases", "__pycache__"}

# The refusals' one definition.
DEFINITION = ("writers/qdrant.py", "PRE_ALIAS_COLLECTION")
# Modules that use "chunks" as the Postgres table's name, or as a report's column heading.
TABLE_NAME_MODULES = {"writers/reader_writer.py", "writers/apply.py",
                      "scripts/export_live_snapshot.py", "scripts/enrichment_sample_run.py"}
# Arguments of writers.qdrant's functions and the Qdrant client's that name a collection.
COLLECTION_ARGS = {"collection_name", "source", "target", "name", "new", "old"}
QDRANT_CALLS = {"upsert_points", "copy_points", "scroll_points", "check_vectors",
                "ensure_collection", "count_points", "clear_staged_points", "retrieve",
                "switch_alias", "create_chunks_collection"}


def _is_chunks(node) -> bool:
    return isinstance(node, ast.Constant) and node.value == "chunks"


def _name_of(node) -> str:
    return getattr(node, "id", None) or getattr(node, "attr", None) or ""


def hits(source: str, relative: str) -> list[str]:
    """Each place `source` names the collection, as `<module>:<line>`."""
    tree = ast.parse(source)
    found, allowed = [], set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not _is_chunks(node.value):
                continue
            names = {_name_of(t) for t in targets}
            if (relative, *names) == DEFINITION:
                allowed.add(id(node.value))
            elif any("COLLECTION" in n.upper() or n.upper() == "CHUNKS" for n in names):
                found.append(node.value)
        elif isinstance(node, ast.Call):
            if _name_of(node.func) in QDRANT_CALLS:
                found.extend(a for a in node.args if _is_chunks(a))
            found.extend(k.value for k in node.keywords
                         if k.arg in COLLECTION_ARGS and _is_chunks(k.value))
    if relative not in TABLE_NAME_MODULES:
        found.extend(n for n in ast.walk(tree) if _is_chunks(n) and id(n) not in allowed)
    return sorted({f"{relative}:{n.lineno}" for n in found})


def _sources():
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT)
        if not SKIPPED_DIRS & set(relative.parts):
            yield path, relative.as_posix()


def test_no_writer_names_the_chunks_collection():
    assert [hit for path, relative in _sources()
            for hit in hits(path.read_text(), relative)] == []


def test_the_refusals_are_the_only_definition():
    source = (ROOT / "writers/qdrant.py").read_text()
    assert 'PRE_ALIAS_COLLECTION = "chunks"' in source
    assert hits(source, "writers/qdrant.py") == []


@pytest.mark.parametrize("line", [
    'QDRANT_COLLECTION = "chunks"',
    'CHUNKS = "chunks"',
    'client.scroll(collection_name="chunks")',
    'upsert_points(client, "chunks", points)',
    'x = "chunks"',
])
def test_the_search_finds_each_way_of_naming_it(line):
    assert hits(line, "stages/embed.py") == ["stages/embed.py:1"]


@pytest.mark.parametrize("line", [
    'QDRANT_COLLECTION = "chunks"',
    'client.scroll(collection_name="chunks")',
    'upsert_points(client, "chunks", points)',
])
def test_a_table_name_module_may_not_name_it_either(line):
    assert hits(line, "writers/apply.py") == ["writers/apply.py:1"]


def test_a_table_name_module_keeps_its_table():
    assert hits('await conn.fetch(_rows_sql("chunks", columns))', "writers/apply.py") == []
