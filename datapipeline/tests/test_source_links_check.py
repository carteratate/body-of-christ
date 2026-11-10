"""checks/source_links.py (2.4e, #292): finds each vatican.va passage's text fragment in
the vendored page, as a browser would, and lists the passages that keep the plain URL."""
import json

import pytest

from checks import source_links as SL

PAGE = """<html><head><title>Gaudium et Spes</title><script>var only = "in the mystery";
</script></head><body>
<p class="toc"><a href="#22">22. Christ the New Man</a></p>
<p>21. The Church holds that the recognition of God is in no way hostile to man's
dignity.</p>
<p>22. The truth is that only in the mystery of the incarnate<sup>20</sup> Word does the
mystery of man take on light.</p>
<p>Cf. Second Vatican Council, Dogmatic Constitution on the Church, n. 8.</p>
<p>Cf. Second Vatican Council, Dogmatic Constitution on the Church, n. 16.</p>
<p>Worker Solidarity</p><p>When dealing with human work in the fundamental dimension</p>
</body></html>"""


def _page(tmp_path):
    path = tmp_path / "gs.html"
    path.write_text(PAGE)
    return str(path)


def test_page_blocks_leave_out_scripts_and_keep_one_string_per_block(tmp_path):
    blocks = SL.page_blocks(_page(tmp_path))
    assert not any("var only" in b for b in blocks)
    assert "worker solidarity" in blocks
    assert any(b.startswith("22. the truth is that only") for b in blocks)


def test_matches_are_whole_words_within_one_block(tmp_path):
    blocks = SL.page_blocks(_page(tmp_path))
    assert len(SL.matches(blocks, "The truth is that only in the mystery")) == 1
    assert SL.matches(blocks, "ruth is that only in the") == []
    # A heading and the paragraph after it are separate blocks.
    assert SL.matches(blocks, "Worker Solidarity When dealing") == []


def test_a_repeat_counts_as_found_only_when_the_passage_is_the_first(tmp_path):
    pages = {"https://www.vatican.va/gs.html": _page(tmp_path)}

    def passage(i, content):
        return {"id": i, "title": "Gaudium et Spes", "url": "https://www.vatican.va/gs.html",
                "content": content}

    outcomes, by_document = SL.classify([
        passage("gs22", "22. The truth is that only in the mystery of the incarnate Word"),
        passage("n8", "Cf. Second Vatican Council, Dogmatic Constitution on the Church, n. 8."),
        passage("n16", "Cf. Second Vatican Council, Dogmatic Constitution on the Church, n. 16."),
        passage("gone", "These words were never written on the page at all"),
        passage("short", "VI"),
        passage("heading", "Worker Solidarity\n\nWhen dealing with human work in the "
                           "fundamental dimension"),
        {**passage("nopage", "The truth is that only in the mystery"), "url": "https://x"},
    ], pages)
    assert outcomes == {"gs22": "found", "n8": "found", "n16": "repeated", "gone": "missing",
                        "short": "no-fragment", "heading": "found", "nopage": "no-page"}
    assert sum(by_document["Gaudium et Spes"].values()) == 7
    assert "miss rate" in SL.report(outcomes, by_document)

    out = tmp_path / "misses.json"
    # A run missing a vendored page must not replace the list.
    with pytest.raises(SystemExit):
        SL.write_misses(outcomes, str(out))
    assert not out.exists()
    del outcomes["nopage"]
    assert SL.write_misses(outcomes, str(out)) == ["gone", "n16"]
    data = json.loads(out.read_text())
    assert data["chunk_ids"] == ["gone", "n16"]
    assert data["counts"]["found"] == 3


def test_the_check_uses_the_api_rule():
    # Loaded by path from services/api/app, so the two cannot drift apart.
    assert SL.source_links.__file__.endswith("services/api/app/source_links.py")
    assert SL.source_links.fragment_text("22. The truth is that only in the mystery of man") \
        == "The truth is that only in the mystery"


def test_a_build_run_changes_only_its_documents_entries_and_a_live_run_keeps_them(tmp_path):
    # 1.3c: the 23 papal documents reach vatican.va only at the publish, so their
    # passages are checked from the build, under the IDs they will carry live.
    out = tmp_path / "misses.json"
    SL.write_misses({"live-a": "missing", "live-b": "found"}, str(out))
    SL.write_misses({"built-a": "repeated", "built-b": "found"}, str(out),
                    build_keys=["encyclicals/humanae-vitae"])
    data = json.loads(out.read_text())
    assert data["chunk_ids"] == ["built-a", "live-a"]
    assert data["counts"] == {"found": 1, "missing": 1}
    assert data["from_build"]["source_keys"] == ["encyclicals/humanae-vitae"]
    assert data["from_build"]["chunk_ids"] == ["built-a"]
    # Rerun from the build: its documents' entries are replaced, not added to.
    SL.write_misses({"built-a": "found", "built-c": "missing"}, str(out),
                    build_keys=["encyclicals/humanae-vitae"])
    assert json.loads(out.read_text())["chunk_ids"] == ["built-c", "live-a"]
    # A live run before the publish does not read them, so it keeps them...
    SL.write_misses({"live-a": "found"}, str(out))
    assert json.loads(out.read_text())["chunk_ids"] == ["built-c"]
    # ... and once they are live, the live run's outcome replaces them.
    SL.write_misses({"live-a": "found", "built-c": "found"}, str(out))
    data = json.loads(out.read_text())
    assert data["chunk_ids"] == [] and "from_build" not in data
