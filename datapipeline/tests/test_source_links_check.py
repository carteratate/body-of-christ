"""checks/source_links.py (2.4e, #292): finds each vatican.va passage's text fragment in
the vendored page, as a browser would, and lists the passages that keep the plain URL."""
import json

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

    out = tmp_path / "misses.json"
    assert SL.write_misses(outcomes, str(out)) == ["gone", "n16"]
    data = json.loads(out.read_text())
    assert data["chunk_ids"] == ["gone", "n16"]
    assert data["counts"]["found"] == 3
    assert "miss rate" in SL.report(outcomes, by_document)


def test_the_check_uses_the_api_rule():
    # Loaded by path from services/api/app, so the two cannot drift apart.
    assert SL.source_links.__file__.endswith("services/api/app/source_links.py")
    assert SL.source_links.fragment_text("22. The truth is that only in the mystery of man") \
        == "The truth is that only in the mystery"
