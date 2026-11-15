"""CCEL's staff blurb in a ThML header (`<description>`) never reaches a passage (3.1;
Decision log "CCEL staff descriptions"): each ThML adapter builds the fixture and no
passage holds its text, and the coverage rule that guards the vendored files finds it
when it does."""
import json
import os
import shutil
from types import SimpleNamespace

from checks import source_text
from ingest import church_fathers, medieval

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "thml_description.xml")
OPENING = "Written in the third century"


def _passages(documents):
    passages = [p for d in documents for p in d.passages]
    assert passages and any("Patience is the companion" in p.content for p in passages)
    return passages


def test_description_is_read_from_the_header():
    text = source_text.thml_description(FIXTURE)
    assert text.startswith(OPENING) and "The Treatise of Testius is the best-known" in text


def test_church_fathers_adapter_leaves_the_description_out():
    passages = _passages(church_fathers.build_documents(FIXTURE))
    assert not [p.anchor for p in passages if OPENING in p.content]
    assert source_text.description_leaks(
        {"thml_description.xml": source_text.thml_description(FIXTURE)}, passages) == []


def test_medieval_adapter_leaves_the_description_out(tmp_path, monkeypatch):
    shutil.copy(FIXTURE, tmp_path / "thml_description.xml")
    (tmp_path / "manifest.json").write_text(json.dumps([{
        "url": "https://example.org/thml_description.xml", "title": "The Treatise of Testius",
        "author": "Testius", "year": 250, "file": "thml_description.xml"}]))
    monkeypatch.setattr(medieval, "_SRC", str(tmp_path))
    passages = _passages(medieval.build_documents())
    assert not [p.anchor for p in passages if OPENING in p.content]


def test_a_leaked_description_is_found():
    description = source_text.thml_description(FIXTURE)
    leaked = SimpleNamespace(anchor="ii.i", content="Chapter I. " + description[10:60])
    clean = SimpleNamespace(anchor="ii.ii", content=description[:39] + " and more.")
    assert source_text.description_leaks({"f.xml": description}, [leaked, clean]) \
        == [("f.xml", "ii.i")]


def test_a_quotation_of_the_author_is_not_a_leak():
    # CCEL's blurb for Anselm quotes the Proslogium; that quotation is Anselm's text.
    description = ('In his Proslogium, St. Anselm presents the Ontological Argument, in '
                   'which God is defined as, "a being than which none greater can be '
                   'conceived." This collection is a fine example of medieval philosophy.')
    quoting = SimpleNamespace(anchor="ii", content="We believe that thou art a being than "
                              "which none greater can be conceived.")
    leaking = SimpleNamespace(anchor="iii", content="This collection is a fine example of "
                              "medieval philosophy.")
    assert source_text.description_leaks({"f.xml": description}, [quoting, leaking]) \
        == [("f.xml", "iii")]

