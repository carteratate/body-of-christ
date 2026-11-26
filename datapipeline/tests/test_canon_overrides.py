"""Canon law current text (corpus-cleanup 1.5b): the De concordia inter Codices English,
the canons with no English (rule E), and the Latin-run check."""
import sys, os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json

import pytest

from checks import source_text
from checks.language import latin_runs
from checks.sequence import canons as canon_sequence
from ingest import canon_overrides as co
from model import Document, Passage
from registry import load_registry, validate

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "canon-law")
_vendored = os.path.exists(os.path.join(_SRC, "overrides.json"))
vendored = pytest.mark.skipif(not _vendored, reason="canon-law overrides not vendored")

LATIN = ("Ecclesiae latinae per receptum baptismum adscribitur filius parentum, qui ad eam "
         "pertineant vel, si alteruter ad eam non pertineat, ambo concordi voluntate optaverint")
ENGLISH = ("Through the reception of baptism a child is ascribed to the Latin Church if the "
           "parents belong to that Church")


def _override(canon=111, field="content", change="replace", text="§1. New text.", **kw):
    row = dict(canon=canon, field=field, change=change, text=text, language="en",
               status=co.UNOFFICIAL_ENGLISH, source_title="t", source_url="https://e/x",
               retrieved="2026-11-11", page_sha256="0" * 64,
               official_latin_url=co.DE_CONCORDIA["url"])
    row.update(kw)
    return co.Override(**row)


def _write(tmp_path, overrides):
    path, index = tmp_path / "overrides.json", tmp_path / "index.csv"
    co.write(overrides, str(path), str(index))
    return str(path), str(index)


# ── The Latin-run check ─────────────────────────────────────────────────────

def test_latin_run_found_in_latin_not_in_english():
    assert latin_runs(LATIN)
    assert latin_runs(ENGLISH) == []
    # Terms of art inside English are English text.
    assert latin_runs("the Church sui iuris, to which the father belongs") == []
    assert latin_runs("a marriage ratum et non consummatum can be dissolved") == []


# ── Applying overrides ──────────────────────────────────────────────────────

def test_override_replaces_content_and_links_latin(tmp_path):
    path, index = _write(tmp_path, [_override(text="§1. " + ENGLISH + ".")])
    overrides = co.load(path, index)
    o = overrides[111]
    assert co.apply(111, "§1. " + LATIN + ".", o) == "§1. " + ENGLISH + "."
    assert o[0].status == co.UNOFFICIAL_ENGLISH
    assert o[0].official_latin_url.startswith("https://www.vatican.va/content/francesco/la/")


def test_override_replaces_or_adds_one_paragraph():
    canon = "§1. One.\n§2. Two, 1983.\n1/ item\n§3. Three."
    assert co.apply(535, canon, [_override(535, "§2", text="§2. Two, 2016.")]) \
        == "§1. One.\n§2. Two, 2016.\n§3. Three."
    assert co.apply(1108, "§1. One.\n§2. Two.", [_override(1108, "§3", "add",
                                                           text="§3. Three.")]) \
        == "§1. One.\n§2. Two.\n§3. Three."
    with pytest.raises(ValueError):
        co.apply(1108, "§1. One.", [_override(1108, "§3", "add", text="§3. Three.")])
    with pytest.raises(ValueError):
        co.apply(535, "§1. One.", [_override(535, "§2", text="§2. Two.")])


def test_override_replaces_one_item_keeping_the_page_marker():
    canon = "§1. For an infant:\n1/ one;\n2/ Latin.\n§2. Two."
    item = _override(868, "§1 2°", text="§1. 2° English, subject to § 3.")
    assert co.apply(868, canon, [item]) \
        == "§1. For an infant:\n1/ one;\n2/ English, subject to § 3.\n§2. Two."
    with pytest.raises(ValueError, match="no single item"):
        co.apply(868, "§1. For an infant:\n1/ one;\n§2. Two.", [item])
    with pytest.raises(ValueError, match="does not open"):
        co.apply(868, canon, [_override(868, "§1 2°", text="2° English.")])


def test_item_field_is_only_replaced(tmp_path):
    path, index = _write(tmp_path, [_override(868, "§1 3°", "add", text="§1. 3° New.")])
    with pytest.raises(ValueError, match="field"):
        co.load(path, index)


def test_override_file_hash_mismatch_fails(tmp_path):
    path, index = _write(tmp_path, [_override()])
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["overrides"][0]["text"] = "§1. Text nobody reviewed."
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    with pytest.raises(ValueError, match="not the one reviewed"):
        co.load(path, index)


def test_override_file_missing_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        co.load(str(tmp_path / "overrides.json"), str(tmp_path / "index.csv"))


def test_canon_without_english_takes_no_override(tmp_path):
    path, index = _write(tmp_path, [_override(canon=295)])
    with pytest.raises(ValueError, match="no English"):
        co.load(path, index)


def _de_concordia_page(texts: dict[int, str]) -> bytes:
    arts = "".join(f"<p>Art. {n}. Can. {n} is replaced by:</p><p>{texts.get(n, '§1. T.')}</p>"
                   for n in range(1, 12))
    return f"<html><body>{arts}<p>I decree that this letter …</p></body></html>".encode()


def test_vendoring_corrects_only_the_declared_typo_and_records_it():
    page = _de_concordia_page({
        1: "§1. One.", 2: "§1. Two.", 3: "§2. Three.", 4: "§1. 2° Four.",
        5: "§3. Impossible for than to obtain access to the actual ministry.",
        6: "§3. Six.", 7: "§1. Seven.", 8: "§1. Eight.", 9: "§1. Nine.", 10: "§3. Ten.",
        11: "§1. Eleven."})
    rows = {(o.canon, o.field): o for o in co.build_overrides(page, "2026-11-22")}
    s3 = rows[(868, "§3")]
    assert s3.text == "§3. Impossible for them to obtain access to the actual ministry."
    assert s3.corrections == (("for than", "for them"),)
    assert "ministrum proprium" in s3.notes and "actual ministry" in s3.notes
    assert rows[(868, "§1 2°")].corrections == () and rows[(111, "content")].notes == ""
    assert "for than -> for them" in co.index_csv(list(rows.values()))
    with pytest.raises(ValueError, match="occurs 0 times"):
        co.build_overrides(page.replace(b"for than", b"for them"), "2026-11-22")


def test_extract_de_concordia_reads_each_article():
    arts = "".join(f"<p>Art. {n}. Can. {n} is replaced by:</p><p>§1. Text {n}.</p>"
                   f"<p>§2. More {n}.</p>" for n in range(1, 12))
    html = f"<html><body><p>Preamble.</p>{arts}<p>I decree that this letter …</p></body></html>"
    texts = co.extract_de_concordia(html)
    assert texts[3] == "§1. Text 3.\n§2. More 3."
    with pytest.raises(ValueError):
        co.extract_de_concordia(html.replace("<p>Art. 11.", "<p>Article eleven."))


# ── Canons with no English ──────────────────────────────────────────────────

def test_canon_without_english_is_retired_with_tombstone():
    reg = load_registry()
    assert validate(reg) == []
    doc = "aa889573-50b2-5a1d-9264-f309583c0c1b"
    entries = {e["anchor"]: e for e in reg.removals
               if e["collection"] == "canon-law" and e["scope"] == "passage"}
    rows = {r["anchor"]: r for r in reg.passages if r["document_id"] == doc}
    assert sorted(co.NO_ENGLISH) == [295, 296, 579, 695, 700]
    for n, spec in co.NO_ENGLISH.items():
        e = entries[f"can/{n}"]
        assert e["reason"] == "translation-in-preparation" and e["added_by"] == "1.5b"
        assert e["tombstone"] == co.tombstone(n) \
            == f"Canon {n} was amended in {spec.year}; no English translation is available."
        assert rows[f"can/{n}"]["status"] == "retired"
        assert e["passage_id"] == rows[f"can/{n}"]["passage_id"]
        # No history passage hangs from a canon with no current one.
        assert not [a for a in rows if a.startswith(f"can/{n}/history-")]
        assert co.latin_urls()[f"can/{n}"] == spec.latin_url
        assert spec.latin_url.startswith("https://www.vatican.va/")
    assert co.document_note() == (
        "Canons 295, 296, 579, 695 and 700 are not shown: their current text has no "
        "English translation. The official Latin is on vatican.va.")


def test_canon_868_returns_under_its_old_ids():
    """#400: rm-1953 is closed, not deleted, and both IDs are the ones 1.5a froze."""
    reg = load_registry()
    entry = next(e for e in reg.removals if e["id"] == "rm-1953")
    assert entry["anchor"] == "can/868" and entry["closed_by"] == "400"
    rows = {r["anchor"]: r for r in reg.passages
            if r["document_id"] == "aa889573-50b2-5a1d-9264-f309583c0c1b"}
    assert rows["can/868"]["passage_id"] == "8559e47c-c102-50bb-92b9-38f0636da9ce"
    assert rows["can/868/history-1983"]["passage_id"] == "dbd3f223-8a1c-57ac-897d-409e2debcd38"
    assert {rows[a]["status"] for a in ("can/868", "can/868/history-1983")} == {"active"}
    assert "can/868" not in co.latin_urls()


def test_withheld_canon_is_neither_missing_nor_allowed():
    def doc(*nums):
        return Document(id="d", collection="canon-law", title="Code", passages=[
            Passage(content="x", reference=f"Can. {n}", anchor=f"can/{n}", chapter_key="k",
                    chapter_label="k", position=i) for i, n in enumerate(nums)])
    everything = [n for n in range(1, 1753) if n not in co.NO_ENGLISH]
    result = canon_sequence([doc(*everything)])
    assert result.missing == [] and result.out_of_range == []
    result = canon_sequence([doc(*everything, 295)])
    assert result.out_of_range == ["295"]


def test_source_text_withholds_latin_and_retired_canons(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(f"""<html><body><table><tr><td>
<p>Can. 294 After the conferences of bishops involved have been heard.</p>
<p>Can. 295 §1. The statutes established by the Apostolic See govern a personal prelature.</p>
<p>§2. The prelate must see to both the spiritual formation and decent support.</p>
<p>Can. 297 The statutes likewise are to define the relations of the personal prelature.</p>
<p>Can. 111 §1. {LATIN}.</p>
<p>§2. {ENGLISH}.</p>
</td></tr></table></body></html>""", encoding="utf-8")
    units = source_text.html_units(str(page), canon_law=True)
    regions = [(u.unit_id, u.region) for u in units if u.region in ("body", "withheld")]
    assert regions == [("294", "body"), ("295", "withheld"), (None, "withheld"),
                       ("297", "body"), ("111", "withheld"), (None, "body")]


# ── Vendored source ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def built():
    from ingest.canon_law import build_documents
    return build_documents()[0]


@vendored
def test_index_lists_every_override_with_its_source():
    overrides = co.load()
    assert sorted(overrides) == [111, 112, 535, 868, 1108, 1109, 1111, 1112, 1116, 1127]
    assert [(o.field, o.change) for o in overrides[868]] == [("§1 2°", "replace"),
                                                              ("§3", "add")]
    assert overrides[868][1].corrections == (("for than", "for them"),)
    for rows in overrides.values():
        for o in rows:
            assert (o.status, o.language, o.source_url) == \
                (co.UNOFFICIAL_ENGLISH, "en", co.EWTN_URL)


@vendored
def test_unofficial_english_canons(built):
    by = {p.anchor: p for p in built.passages}
    for n in (111, 112, 535, 868, 1108, 1109, 1111, 1112, 1116, 1127):
        p = by[f"can/{n}"]
        assert p.searchable and latin_runs(p.content) == [], n
        assert p.metadata["text_status"] == "unofficial_english"
        assert p.metadata["official_latin_url"] == co.DE_CONCORDIA["url"]
        assert p.metadata["text_replaced"]
        assert p.metadata["amended"] and "De concordia" in p.metadata["amended_by"]["title"]
        assert f"can/{n}/history-1983" in by, n
    assert by["can/111"].content.startswith("§1. Through the reception of baptism a child")
    assert "ascription to a Church" in by["can/535"].content.split("\n§2.")[1]
    assert by["can/1108"].content.split("\n")[-1].startswith("§3. Only a priest validly")
    assert "ascribed to the Latin Church" in by["can/1109"].content
    assert "of the Latin rite" in by["can/1109/history-1983"].content
    assert by["can/1116"].content.split("\n")[-1].startswith("§3. In addition")
    c868 = by["can/868"].content.split("\n")
    assert c868[2].startswith("2/ there must be a founded hope") and "subject to § 3" in c868[2]
    assert c868[-1] == ("§3. An infant of non-Catholic Christian parents is baptized licitly "
                        "if the parents, or at least one of them or the person who lawfully "
                        "takes their place requests it and if it is physically or morally "
                        "impossible for them to obtain access to the actual ministry.")
    assert by["can/868/history-1983"].content.startswith(
        "§1. 2/ there must be a founded hope")
    assert not by["can/868/history-1983"].searchable


@vendored
def test_no_english_canons_are_not_built(built):
    anchors = {p.anchor for p in built.passages}
    for n in co.NO_ENGLISH:
        assert not [a for a in anchors if a == f"can/{n}" or a.startswith(f"can/{n}/")]
    assert built.notes == co.document_note()
    assert built.metadata["official_latin_urls"] == co.latin_urls()


@vendored
def test_no_canon_passage_has_a_latin_run(built):
    assert [(p.anchor, latin_runs(p.content)) for p in built.passages
            if latin_runs(p.content)] == []
