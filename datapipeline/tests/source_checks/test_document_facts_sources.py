"""Document facts against the vendored sources (corpus-cleanup 2.3)."""
from __future__ import annotations

import glob
import os
import re
import sys

import registry
import rights_inventory
from checks import dating_lines
from checks.source_text import SOURCES
from tests.source_checks.conftest import needs_sources

sys.path.insert(0, os.path.join(os.path.dirname(registry.REGISTRY_DIR), "scripts"))
import document_facts_registry  # noqa: E402


@needs_sources
def test_registry_facts_match_the_build(built):
    """works.json holds what scripts/document_facts_registry.py derives from today's
    build: an adapter's year or notes, a papal genre or a credit line that changes
    without a rerun fails here."""
    reg = registry.load_registry()
    held = registry.removed_document_ids(reg)
    documents = [registry.drop_removed(d, reg) for docs in built.values() for d in docs
                 if d.id not in held]
    works = document_facts_registry.generate(reg, documents, rights_inventory.load())
    stale = [w["work_id"] for w, old in zip(works, reg.works) if w != old]
    assert stale == [], "rerun scripts/document_facts_registry.py"


@needs_sources
def test_papal_years_equal_their_dating_lines():
    reg = registry.load_registry()
    years = {w["source_key"]: w["year"] for w in reg.works if registry.has_facts(w)}
    dated, wrong = dating_lines.mismatches(years)
    assert dated >= 150, "the dating-line pattern stopped finding the pages' dating lines"
    assert wrong == []


@needs_sources
def test_a_wrong_year_is_caught_through_markup_and_ordinals():
    """Dating lines broken by inline markup (Providentissimus Deus's line break, Evangelii
    Gaudium's italic "Year of Faith") or printing an ordinal year (Quo Graviora's
    "1826th") are read, so a wrong registry year there fails."""
    reg = registry.load_registry()
    years = {w["source_key"]: w["year"] for w in reg.works if registry.has_facts(w)}
    for key in ("encyclicals/providentissimus-deus", "encyclicals/quo-graviora",
                "encyclicals/evangelii-gaudium"):
        wrong = dating_lines.mismatches({**years, key: 1900})[1]
        assert [k for k, _, _ in wrong] == [key], key


@needs_sources
def test_cum_sancta_mater_ecclesia_is_dated_1859():
    path = os.path.join(SOURCES, "encyclicals", "cum-sancta-mater-ecclesia.html")
    assert dating_lines.printed_year(path) == 1859


def _descriptions() -> list[str]:
    out = []
    for path in glob.glob(os.path.join(SOURCES, "*", "*.xml")):
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for m in re.finditer(r"<description>(.*?)</description>", text, re.S):
            blurb = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()
            if blurb:
                out.append(blurb.lower())
    return out


@needs_sources
def test_no_thml_description_text_in_the_registry():
    """No registry field is taken from a ThML `<description>` blurb (2.3): neither a whole
    field found inside one, nor a sentence of one inside a field."""
    blurbs = _descriptions()
    assert blurbs, "no <description> found in the vendored ThML files"
    sentences = {s.strip() for b in blurbs for s in re.split(r"(?<=[.!?])\s", b)
                 if len(s.strip()) >= 40}
    # The prose fields; a title or council name rightly appears in its blurb.
    fields = ("translation", "source_credit", "notes", "attribution_note",
              "date_display", "superseded_note")
    hits = []
    for w in registry.load_registry().works:
        for k in fields:
            value = re.sub(r"\s+", " ", str(w.get(k) or "")).lower()
            if len(value) >= 40 and any(value in b for b in blurbs):
                hits.append((w["work_id"], k))
            elif any(s in value for s in sentences):
                hits.append((w["work_id"], k))
    assert hits == []
