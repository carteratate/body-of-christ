"""The Summa corrections file (R7, ingest/summa_corrections.json) keeps its format.

1.7 reads the file to correct roles, numbers and reply targets; R7 wrote it from the
Leonine census and the printed edition. These tests check its shape on the tracked file
and on small fixtures, and (with sources) that every key is a paragraph of summa.xml.
"""
import json
import os
import re

import pytest

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILE = os.path.join(_HERE, "ingest", "summa_corrections.json")
_SRC = os.path.join(_HERE, "sources", "summa", "summa.xml")

PARA_ID = re.compile(r"^(FP|FS|SS|TP|XP)_Q\d+(_A\d+)?-p\d+$")
ARTICLE_ID = re.compile(r"^(FP|FS|SS|TP|XP)_Q\d+(_A\d+)?$")
TARGET = re.compile(r"^(obj|sc) \d+$")
LATIN = re.compile(r"(\[CT \d+\]|Leonine vol\. 12|^(I|I-II|II-II|III) q\. \d+( a\. \d+)?$)")
FIELDS = {"role", "number", "targets", "also_answers", "holds", "parts", "move_to", "duplicate_of",
          "flag", "source_label", "class", "defect", "latin", "source_note", "printed", "note"}


def problems(doc):
    """Every way the file breaks its format, as short messages (empty when it is valid)."""
    out = []
    roles, classes, flags = set(doc["roles"]), set(doc["classes"]), set(doc["flags"])
    prints = set(doc["print"])
    for pid, e in doc["paragraphs"].items():
        if not PARA_ID.match(pid):
            out.append(f"{pid}: not a source paragraph id")
        if set(e) - FIELDS:
            out.append(f"{pid}: unknown fields {sorted(set(e) - FIELDS)}")
        if "role" in e and e["role"] not in roles:
            out.append(f"{pid}: role {e['role']!r}")
        if e.get("class") not in classes:
            out.append(f"{pid}: class {e.get('class')!r}")
        if "flag" in e and e["flag"] not in flags:
            out.append(f"{pid}: flag {e['flag']!r}")
        if e.get("defect") not in (None, "ccel", "translators"):
            out.append(f"{pid}: defect {e['defect']!r}")
        for f in ("targets", "also_answers", "holds"):
            for t in e.get(f, []):
                if not TARGET.match(t) and not (f == "holds" and t == "co"):
                    out.append(f"{pid}: {f} {t!r}")
        if e.get("role") == "reply" and not e.get("targets"):
            out.append(f"{pid}: a reply with no targets")
        latin = e.get("latin", [])
        if not latin and not e.get("source_note"):
            out.append(f"{pid}: cites no Latin unit or source note")
        for c in latin:
            if not LATIN.search(c):
                out.append(f"{pid}: Latin citation {c!r}")
        if "move_to" in e and not ARTICLE_ID.match(e["move_to"]):
            out.append(f"{pid}: move_to {e['move_to']!r}")
        if "duplicate_of" in e and e["duplicate_of"] not in doc["paragraphs"] and not PARA_ID.match(e["duplicate_of"]):
            out.append(f"{pid}: duplicate_of {e['duplicate_of']!r}")
        if "printed" in e and e["printed"].get("source") not in prints:
            out.append(f"{pid}: printed source {e['printed'].get('source')!r}")
        if len(e.get("source_label") or "") > 30:
            out.append(f"{pid}: source_label is longer than a label")
    for aid, a in doc["articles"].items():
        if not ARTICLE_ID.match(aid):
            out.append(f"{aid}: not an article id")
        for m in a.get("missing", []):
            if m.get("missing") is not True or not m.get("unit") or not m.get("latin"):
                out.append(f"{aid}: a missing unit needs unit, missing and latin")
            if m.get("defect") not in ("ccel", "translators"):
                out.append(f"{aid}: missing unit defect {m.get('defect')!r}")
            if not PARA_ID.match(m.get("after", "")):
                out.append(f"{aid}: missing unit 'after' {m.get('after')!r}")
            for k in ("printed", "other_edition", "printed_also"):
                if k in m and m[k] and m[k]["source"] not in prints:
                    out.append(f"{aid}: {k} source {m[k]['source']!r}")
    return out


def _minimal(**para):
    return {"roles": ["objection", "sed-contra", "determination", "reply", "article-title", "editorial", "duplicate"],
            "classes": ["prose-reply", "joint-reply", "variant", "source-error", "omission"],
            "flags": ["editorial", "editor-supplied", "not-in-leonine"],
            "print": {"dom2-v4": {}},
            "paragraphs": {"FP_Q76_A3-p4": para}, "articles": {}}


def test_tracked_file_is_valid():
    doc = json.load(open(_FILE, encoding="utf-8"))
    assert problems(doc) == []


def test_tracked_file_holds_no_passage_text():
    raw = open(_FILE, encoding="utf-8").read()
    doc = json.loads(raw)
    for pid, e in doc["paragraphs"].items():
        for k in ("note", "source_note"):
            assert len(e.get(k, "")) <= 200, pid


def test_valid_fixture_passes():
    doc = _minimal(role="objection", number=4, source_label="Objection 3", **{"class": "source-error"},
                   defect="ccel", latin=["I q. 76 a. 3 arg. 4 [CT 31535]"], printed={"source": "dom2-v4", "page": "35"})
    assert problems(doc) == []


@pytest.mark.parametrize("bad, expected", [
    ({"role": "speech", "class": "variant", "latin": ["I q. 1 a. 1 co. [CT 1]"]}, "role"),
    ({"role": "reply", "class": "prose-reply", "latin": ["I q. 1 a. 1 ad 1 [CT 1]"]}, "no targets"),
    ({"role": "reply", "targets": ["objection 2"], "class": "prose-reply", "latin": ["I q. 1 a. 1 ad 2 [CT 1]"]}, "targets"),
    ({"role": "objection", "number": 2, "class": "source-error"}, "cites no Latin"),
    ({"role": "objection", "class": "source-error", "latin": ["somewhere"]}, "Latin citation"),
    ({"role": "objection", "class": "guess", "latin": ["I q. 1 a. 1 arg. 1 [CT 1]"]}, "class"),
    ({"role": "objection", "class": "variant", "latin": ["I q. 1 a. 1 arg. 1 [CT 1]"], "text": "It would seem"}, "unknown fields"),
])
def test_fixture_errors_are_reported(bad, expected):
    assert any(expected in p for p in problems(_minimal(**bad)))


@pytest.mark.sources
@pytest.mark.skipif(not os.path.exists(_SRC), reason="summa sources not vendored; run scripts/vendor_sources.py")
def test_every_key_is_a_paragraph_of_the_source():
    ids = set(re.findall(r'<p id="([A-Z0-9_]+-p\d+)"', open(_SRC, encoding="utf-8").read()))
    doc = json.load(open(_FILE, encoding="utf-8"))
    keys = set(doc["paragraphs"])
    refs = {m["after"] for a in doc["articles"].values() for m in a.get("missing", [])}
    refs |= {e["duplicate_of"] for e in doc["paragraphs"].values() if "duplicate_of" in e}
    refs |= {a["first_paragraph"] for a in doc["articles"].values() if "first_paragraph" in a}
    assert sorted((keys | refs) - ids) == []
