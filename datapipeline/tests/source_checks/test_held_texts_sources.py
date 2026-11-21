"""Held texts against the build from the vendored sources (corpus-cleanup 4.3): every
open entry follows a passage the build emits, in order, and each document carries its
whole list. Needs the gitignored datapipeline/sources/; CI runs the source-free check in
tests/test_held_texts.py."""
import registry
from publication import build
from tests.source_checks.conftest import needs_sources

COLLECTIONS = ("councils", "encyclicals", "papal-documents")


@needs_sources
def test_the_shipped_list_fits_the_build(built):
    entries = registry.open_held_texts(registry.current())
    expected: dict[str, int] = {}
    for h in entries:
        expected[h["document_id"]] = expected.get(h["document_id"], 0) + 1
    found = {}
    for collection in COLLECTIONS:
        # build() runs the coverage and placement checks; it raises on a stranded list.
        for d in build(collection, source_adapters={collection: lambda c=collection: built[c]}):
            if d.metadata and d.metadata.get("held_texts"):
                found[d.id] = len(d.metadata["held_texts"])
    assert found == expected
