"""1.10b on the vendored sources: no translator note's text in a Fathers or medieval
passage's text, every verse block of a built chapter read, the Summa read as before,
every kept footnote a scripture reference placed after a word, and the removal
registry's note counts equal to the build's."""
import os
from collections import defaultdict
from functools import lru_cache
from xml.etree.ElementTree import tostring

import pytest

import registry
from checks.source_text import SOURCES
from ingest.church_fathers import _read_root
from ingest.common import _block_text, _blocks, _extract_p_text, _strip_tags, direct_blocks
from ingest.scripture_notes import scripture_reference
from normalize.text import clean_text
from release.remap import words
from tests.source_checks.conftest import needs_sources

pytestmark = [pytest.mark.sources, needs_sources]

THML = ("church-fathers", "medieval")
NOTE_MIN = 20


def _flat(text: str) -> str:
    return " ".join(clean_text(text).split())


@lru_cache(maxsize=None)
def _root(collection: str, name: str):
    return _read_root(os.path.join(SOURCES, collection, name))


def _notes(element) -> list:
    """The <note> elements under element that no other note holds."""
    out = []
    for child in element:
        if child.tag == "note":
            out.append(child)
        else:
            out += _notes(child)
    return out


def _by_file(built) -> dict:
    out = defaultdict(list)
    for collection in THML:
        for d in built[collection]:
            for p in d.passages:
                out[(collection, p.metadata["source_file"])].append(p)
    return out


def test_no_note_text_in_passages(built):
    leaks = []
    for (collection, name), passages in sorted(_by_file(built).items()):
        root = _root(collection, name)
        body = " | ".join(_flat(_block_text(b)) for b in _blocks(root))
        corpus = " | ".join(" ".join(p.content.split()) for p in passages)
        for note in _notes(root):
            text = _flat(_strip_tags(tostring(note, encoding="unicode")))
            # An editor's note may repeat the author's own words; those stay.
            if len(text) >= NOTE_MIN and text not in body and text in corpus:
                leaks.append((name, note.get("id"), text[:80]))
    assert leaks == []


def test_every_verse_block_of_a_built_chapter_is_read(built):
    missing = []
    for (collection, name), passages in sorted(_by_file(built).items()):
        chapters = defaultdict(list)
        for p in passages:
            chapters[p.chapter_key].append(p)
        divs = {e.get("id"): e for e in _root(collection, name).iter()
                if isinstance(e.tag, str) and e.tag.startswith("div")}
        for key, members in chapters.items():
            read = " " + " ".join(w for p in members for w in words(p.content)) + " "
            for block in direct_blocks(divs[key]):
                if block.tag != "verse":
                    continue
                verse = " ".join(words(clean_text(_block_text(block))))
                if verse and f" {verse} " not in read:
                    missing.append((name, block.get("id")))
    assert missing == []


def test_summa_is_read_as_before():
    # The Summa has no <note> or <verse>, so reading notes out changes none of its text.
    root = _read_root(os.path.join(SOURCES, "summa", "summa.xml"))
    assert next(root.iter("note"), None) is None and next(root.iter("verse"), None) is None
    for div4 in root.iter("div4"):
        before = [_strip_tags(tostring(p, encoding="unicode", method="xml"))
                  for p in div4.iter("p")]
        assert _extract_p_text(div4) == "\n\n".join(t for t in before if t)


def test_note_class_entries_match_the_build(built):
    counts = {d.id: sum((p.metadata or {}).get("editor_note_count", 0) for p in d.passages)
              for c in THML for d in built[c]}
    # An entry closes when a later item removes every note it counted (1.8a's editor
    # matter held all of two documents' notes).
    entries = {e["document_id"]: e["span"]["count"] for e in registry.load_registry().removals
               if e["added_by"] == "1.10b" and e["scope"] == "class" and not e.get("closed_by")}
    assert entries == {d: n for d, n in counts.items() if n}



def test_footnotes_are_scripture_references_after_a_word(built):
    bad, total = [], {c: 0 for c in THML}
    for c in THML:
        for d in built[c]:
            for p in d.passages:
                notes = (p.metadata or {}).get("footnotes", [])
                total[c] += len(notes)
                if [n["n"] for n in notes] != list(range(1, len(notes) + 1)):
                    bad.append((p.anchor, "numbering"))
                for n in notes:
                    if scripture_reference(n["text"]) != n["text"] \
                            or not 0 < n["at"] <= len(p.content) \
                            or p.content[n["at"] - 1].isspace():
                        bad.append((p.anchor, n))
    # The Imitation prints its references in Arabic numerals ("Luke 17:21.").
    assert bad == [] and total["church-fathers"] > 14000 and total["medieval"] >= 50
