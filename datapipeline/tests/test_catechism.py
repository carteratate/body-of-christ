"""Tests for the three-tier CCC page_node chunking strategy.

All tests are self-contained — no filesystem or database access.
"""
import sys, os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.catechism import (
    chunk_nodes,
    extract_node_text,
    is_section_header,
    make_reference,
    split_large_node,
)


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _make_para(text: str = "", ref_ccc: int | None = None, indent: bool = False) -> dict:
    elements: list[dict] = []
    if ref_ccc is not None:
        elements.append({"type": "ref-ccc", "ref_number": ref_ccc})
    if text:
        elements.append({"type": "text", "text": text})
    para: dict = {"elements": elements}
    if indent:
        para["indent"] = True
    return para


def _make_node(*paras: dict) -> dict:
    return {"paragraphs": list(paras)}


# ---------------------------------------------------------------------------
# 1. extract_node_text
# ---------------------------------------------------------------------------

def test_extract_text_collects_text_and_para_numbers():
    node = _make_node(
        _make_para("Hello world", ref_ccc=1),
        _make_para("Second paragraph", ref_ccc=2),
    )
    text, paras = extract_node_text(node)
    assert "Hello world" in text
    assert "Second paragraph" in text
    assert paras == [1, 2]


def test_extract_text_ignores_ref_and_anchor_elements():
    node = {"paragraphs": [{
        "elements": [
            {"type": "ref-ccc", "ref_number": 5},
            {"type": "text", "text": "Main content."},
            {"type": "ref", "number": 3},
            {"type": "ref-anchor", "id": "a1"},
            {"type": "spacer"},
        ]
    }]}
    text, paras = extract_node_text(node)
    assert text == "Main content."
    assert paras == [5]


def test_extract_text_joins_paragraphs_with_double_newline():
    node = _make_node(_make_para("First."), _make_para("Second."))
    text, _ = extract_node_text(node)
    assert text == "First.\n\nSecond."


def test_extract_text_empty_node():
    text, paras = extract_node_text({"paragraphs": []})
    assert text == ""
    assert paras == []


def test_extract_text_multiple_text_elements_joined_with_space():
    node = {"paragraphs": [{
        "elements": [
            {"type": "ref-ccc", "ref_number": 10},
            {"type": "text", "text": "Part one."},
            {"type": "ref", "number": 1},
            {"type": "text", "text": "Part two."},
        ]
    }]}
    text, _ = extract_node_text(node)
    assert text == "Part one. Part two."


def test_extract_text_skips_empty_paragraphs():
    node = {"paragraphs": [
        {"elements": [{"type": "spacer"}]},
        {"elements": [{"type": "text", "text": "Real content."}]},
    ]}
    text, _ = extract_node_text(node)
    assert text == "Real content."
    assert "\n\n" not in text


# ---------------------------------------------------------------------------
# 2. is_section_header
# ---------------------------------------------------------------------------

def test_is_section_header_true_for_short_no_ref_ccc_no_indent():
    assert is_section_header(_make_para("Article 1")) is True


def test_is_section_header_false_when_has_ref_ccc():
    assert is_section_header(_make_para("Some text", ref_ccc=100)) is False


def test_is_section_header_false_when_indented():
    assert is_section_header(_make_para("Short text", indent=True)) is False


def test_is_section_header_false_when_text_ge_120_chars():
    assert is_section_header(_make_para("x" * 120)) is False


def test_is_section_header_true_at_119_chars():
    assert is_section_header(_make_para("x" * 119)) is True


def test_is_section_header_false_when_empty_text():
    assert is_section_header(_make_para("")) is False


def test_is_section_header_false_for_sentence_continuation():
    assert is_section_header(
        _make_para("and St. Ambrose says about this conversion:")
    ) is False


def test_is_section_header_false_when_no_elements():
    assert is_section_header({"elements": []}) is False


# ---------------------------------------------------------------------------
# 3. split_large_node — section boundaries
# ---------------------------------------------------------------------------

def test_split_splits_at_header():
    node = _make_node(
        _make_para("x" * 200, ref_ccc=1),
        _make_para("Section Header"),
        _make_para("y" * 200, ref_ccc=2),
    )
    sections = split_large_node(node)
    assert len(sections) == 2
    assert sections[0][1] == [1]
    assert sections[1][1] == [2]


def test_split_no_headers_returns_one_section():
    node = _make_node(
        _make_para("First.", ref_ccc=10),
        _make_para("Second.", ref_ccc=11),
    )
    sections = split_large_node(node)
    assert len(sections) == 1
    assert sections[0][1] == [10, 11]


def test_split_header_is_first_line_of_its_section():
    node = _make_node(
        _make_para("Intro."),
        _make_para("MY HEADER"),
        _make_para("Body.", ref_ccc=5),
    )
    sections = split_large_node(node)
    assert len(sections) == 2
    assert sections[1][0].startswith("MY HEADER")


def test_split_multiple_headers_produce_multiple_sections():
    node = _make_node(
        _make_para("Intro.", ref_ccc=1),
        _make_para("Header A"),
        _make_para("Body A.", ref_ccc=2),
        _make_para("Header B"),
        _make_para("Body B.", ref_ccc=3),
    )
    sections = split_large_node(node)
    assert len(sections) == 3
    assert sections[0][1] == [1]
    assert sections[1][1] == [2]
    assert sections[2][1] == [3]


def test_split_discards_empty_pre_header_section():
    node = _make_node(
        _make_para("Header Only"),
        _make_para("Body.", ref_ccc=7),
    )
    sections = split_large_node(node)
    assert len(sections) == 1
    text, paras, _ = sections[0]
    assert "Header Only" in text
    assert paras == [7]


# ---------------------------------------------------------------------------
# 4. IN BRIEF detection
# ---------------------------------------------------------------------------

def test_split_in_brief_header_sets_flag():
    node = _make_node(
        _make_para("Regular content.", ref_ccc=100),
        _make_para("IN BRIEF"),
        # ref_ccc prevents short text from being classified as a section header,
        # so this paragraph is treated as body content inside the IN BRIEF section
        _make_para("Summary of the key points.", ref_ccc=101),
    )
    sections = split_large_node(node)
    assert len(sections) == 2
    assert sections[0][2] is False
    assert sections[1][2] is True


def test_split_non_in_brief_header_does_not_set_flag():
    node = _make_node(
        _make_para("Content.", ref_ccc=1),
        _make_para("Other Header"),
        _make_para("More.", ref_ccc=2),
    )
    sections = split_large_node(node)
    assert all(s[2] is False for s in sections)


def test_chunk_nodes_tier2_in_brief_by_raw_text_prefix():
    node = _make_node(
        _make_para("IN BRIEF", ref_ccc=200),
        _make_para("Brief summary here." * 10, ref_ccc=201),
    )
    result = chunk_nodes([node], ["toc-50"])
    _, _, meta, _ = result[0]
    assert meta["is_in_brief"] is True


def test_chunk_nodes_tier2_in_brief_by_header_paragraph():
    in_brief_hdr = _make_para("IN BRIEF")
    body = _make_para("x" * 600, ref_ccc=202)
    result = chunk_nodes([_make_node(in_brief_hdr, body)], ["toc-51"])
    _, _, meta, _ = result[0]
    assert meta["is_in_brief"] is True


def test_chunk_nodes_tier2_regular_node_is_brief_false():
    node = _make_node(_make_para("x" * 600, ref_ccc=300))
    _, _, meta, _ = chunk_nodes([node], ["toc-60"])[0]
    assert meta["is_in_brief"] is False


# ---------------------------------------------------------------------------
# 5. Tier 1 stub merge
# ---------------------------------------------------------------------------

def test_stub_prefix_prepended_to_next_chunk():
    stub = _make_node(_make_para("Section Title"))
    normal = _make_node(_make_para("x" * 600, ref_ccc=10))
    result = chunk_nodes([stub, normal], ["toc-1", "toc-2"])
    assert len(result) == 1
    assert "Section Title" in result[0][0]


def test_stub_prefix_appears_before_node_content():
    stub = _make_node(_make_para("STUB TEXT"))
    normal = _make_node(_make_para("NORMAL TEXT" * 55, ref_ccc=1))
    result = chunk_nodes([stub, normal], ["toc-1", "toc-2"])
    content = result[0][0]
    assert content.index("STUB TEXT") < content.index("NORMAL TEXT")


def test_multiple_stubs_all_merged_into_next_chunk():
    stub1 = _make_node(_make_para("Title One"))
    stub2 = _make_node(_make_para("Title Two"))
    normal = _make_node(_make_para("y" * 600, ref_ccc=5))
    result = chunk_nodes([stub1, stub2, normal], ["toc-1", "toc-2", "toc-3"])
    assert len(result) == 1
    content = result[0][0]
    assert "Title One" in content
    assert "Title Two" in content


def test_no_stub_no_prefix_in_content():
    normal = _make_node(_make_para("x" * 600, ref_ccc=20))
    content = chunk_nodes([normal], ["toc-1"])[0][0]
    assert content == "x" * 600


def test_stub_followed_by_another_stub_then_normal():
    s1 = _make_node(_make_para("A" * 10))
    s2 = _make_node(_make_para("B" * 10))
    normal = _make_node(_make_para("C" * 600, ref_ccc=99))
    result = chunk_nodes([s1, s2, normal], ["toc-1", "toc-2", "toc-3"])
    assert len(result) == 1
    content = result[0][0]
    assert "A" * 10 in content
    assert "B" * 10 in content
    assert "C" * 600 in content


# ---------------------------------------------------------------------------
# 6. Tier 2 — one chunk per normal node
# ---------------------------------------------------------------------------

def test_tier2_produces_exactly_one_chunk():
    node = _make_node(_make_para("x" * 600, ref_ccc=50))
    assert len(chunk_nodes([node], ["toc-10"])) == 1


def test_tier2_reference_single_para():
    node = _make_node(_make_para("x" * 600, ref_ccc=50))
    _, ref, _, _ = chunk_nodes([node], ["toc-10"])[0]
    assert ref == "CCC §50"


def test_tier2_metadata_correct():
    node = _make_node(
        _make_para("x" * 300, ref_ccc=70),
        _make_para("y" * 300, ref_ccc=71),
    )
    _, _, meta, pos = chunk_nodes([node], ["toc-20"])[0]
    assert meta["path"] == "toc-20"
    assert meta["ccc_paragraphs"] == [70, 71]
    assert meta["is_in_brief"] is False
    assert pos == 0


def test_tier2_positions_sequential_across_nodes():
    nodes = [
        _make_node(_make_para("x" * 600, ref_ccc=1)),
        _make_node(_make_para("y" * 600, ref_ccc=2)),
        _make_node(_make_para("z" * 600, ref_ccc=3)),
    ]
    result = chunk_nodes(nodes, ["toc-1", "toc-2", "toc-3"])
    assert [c[3] for c in result] == [0, 1, 2]


def test_tier2_node_with_paras_and_short_text_is_not_stub():
    node = _make_node(_make_para("Short text", ref_ccc=99))
    result = chunk_nodes([node], ["toc-5"])
    assert len(result) == 1
    assert result[0][2]["ccc_paragraphs"] == [99]


def test_tier2_reference_range_for_consecutive_paras():
    node = _make_node(
        _make_para("x" * 300, ref_ccc=10),
        _make_para("y" * 300, ref_ccc=11),
    )
    _, ref, _, _ = chunk_nodes([node], ["toc-1"])[0]
    assert ref == "CCC §10–11"


# ---------------------------------------------------------------------------
# 7. Tier 3 — large node split into multiple chunks
# ---------------------------------------------------------------------------

def _large_node_with_headers() -> dict:
    return _make_node(
        _make_para("x" * 2000, ref_ccc=200),
        _make_para("Chapter One"),
        _make_para("y" * 2100, ref_ccc=201),
    )


def test_tier3_produces_multiple_chunks():
    result = chunk_nodes([_large_node_with_headers()], ["toc-100"])
    assert len(result) > 1


def test_tier3_first_chunk_has_pre_header_content():
    result = chunk_nodes([_large_node_with_headers()], ["toc-100"])
    assert "x" * 100 in result[0][0]


def test_tier3_second_chunk_starts_with_header():
    result = chunk_nodes([_large_node_with_headers()], ["toc-100"])
    assert result[1][0].startswith("Chapter One")


def test_tier3_references_include_part_for_numbered_sections():
    result = chunk_nodes([_large_node_with_headers()], ["toc-100"])
    for _, ref, meta, _ in result:
        if meta["ccc_paragraphs"]:
            assert "(part)" in ref


def test_tier3_positions_are_sequential():
    result = chunk_nodes([_large_node_with_headers()], ["toc-100"])
    assert [c[3] for c in result] == list(range(len(result)))


def test_tier3_in_brief_section_flagged():
    node = _make_node(
        _make_para("x" * 2000, ref_ccc=300),
        _make_para("IN BRIEF"),
        _make_para("y" * 2100),
    )
    result = chunk_nodes([node], ["toc-200"])
    brief_chunks = [c for c in result if c[2]["is_in_brief"]]
    assert len(brief_chunks) >= 1


def test_tier3_unnumbered_section_reference_has_no_part_suffix():
    """A Tier-3 split section with no CCC paragraph numbers gets 'CCC [node_id]',
    not 'CCC [node_id] (part)' — make_reference ignores is_partial when list is empty."""
    node = _make_node(
        _make_para("Intro section."),             # no ref_ccc → first section has no paras
        _make_para("Heading A"),                  # section header
        _make_para("x" * 4200, ref_ccc=500),     # large body triggers Tier 3
    )
    result = chunk_nodes([node], ["toc-77"])
    unnumbered = [c for c in result if not c[2]["ccc_paragraphs"]]
    for _, ref, _, _ in unnumbered:
        assert "(part)" not in ref
        assert "toc-77" in ref


def test_tier3_non_large_node_not_split():
    node = _make_node(
        _make_para("x" * 1000, ref_ccc=400),
        _make_para("Section Header"),
        _make_para("y" * 1000, ref_ccc=401),
    )
    result = chunk_nodes([node], ["toc-50"])
    assert len(result) == 1


def test_tier3_stub_prefix_prepended_to_first_section():
    stub = _make_node(_make_para("Section Intro"))
    large = _large_node_with_headers()
    result = chunk_nodes([stub, large], ["toc-1", "toc-2"])
    assert "Section Intro" in result[0][0]


# ---------------------------------------------------------------------------
# 8. make_reference
# ---------------------------------------------------------------------------

def test_make_ref_empty_uses_node_id():
    assert make_reference([], "toc-5") == "CCC [toc-5]"


def test_make_ref_single():
    assert make_reference([100], "x") == "CCC §100"


def test_make_ref_consecutive_range():
    assert make_reference([100, 101, 102], "x") == "CCC §100–102"


def test_make_ref_non_contiguous():
    assert make_reference([100, 102, 105], "x") == "CCC §100, §102, §105"


def test_make_ref_single_partial():
    assert make_reference([50], "x", is_partial=True) == "CCC §50 (part)"


def test_make_ref_range_partial():
    assert make_reference([50, 51, 52], "x", is_partial=True) == "CCC §50–52 (part)"


def test_make_ref_non_contiguous_partial():
    assert make_reference([50, 52], "x", is_partial=True) == "CCC §50, §52 (part)"


def test_make_ref_empty_with_is_partial_no_part_suffix():
    result = make_reference([], "toc-5", is_partial=True)
    assert result == "CCC [toc-5]"
    assert "(part)" not in result


def test_make_ref_two_consecutive():
    assert make_reference([10, 11], "x") == "CCC §10–11"


def test_make_ref_two_non_consecutive():
    assert make_reference([10, 12], "x") == "CCC §10, §12"


# ---------------------------------------------------------------------------
# US edition (issue #279): fixtures tests/fixtures/ccc_min.json + ccc_us_min.json
# ---------------------------------------------------------------------------

import copy  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402

from ingest import catechism as _catechism, catechism_us as _cu  # noqa: E402
from ingest.ccc_us import drop_repeated_structure, parse_page, resolve  # noqa: E402

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
_SRC = os.path.join(_FIXTURES, "ccc_min.json")
_US = os.path.join(_FIXTURES, "ccc_us_min.json")


@pytest.fixture(scope="module")
def us_build():
    return _catechism.build(_SRC, _US)


def _passage_with(build, n):
    return next(p for p in build.document.passages if n in p.metadata["ccc_paragraphs"])


def test_numbered_paragraph_uses_us_text(us_build):
    content = _passage_with(us_build, 1).content
    assert "Redeemer and Savior." in content
    assert "Saviour" not in content
    assert "Legitimate defense" in _passage_with(us_build, 7).content


def test_ccc_2267_2018_text(us_build):
    content = _passage_with(us_build, 2267).content
    assert "inadmissible" in content
    assert "practically non-existent" not in content


def test_short_continuation_lines_kept_once(us_build):
    content = _passage_with(us_build, 2).content
    us_text = ("So that this call should resound, Christ sent forth the apostles he had chosen, "
               "and they went forth and preached everywhere.")
    assert content.count(us_text) == 1
    assert content.count("preached everywhere") == 1
    # The heading glued onto the last line is still its own heading, after the paragraph.
    assert f"{us_text}\n\nII. HANDING ON THE FAITH\n\nThose who welcomed" in content


def test_headings_use_us_text(us_build):
    first = _passage_with(us_build, 1).content
    assert first.startswith('PROLOGUE\n\n"God our Savior desires all men to be saved."')
    assert "I. THE LIFE OF MAN — TO KNOW AND LOVE GOD" in first
    assert "The life of man - to know" not in first
    # A misprinted source heading takes the US words; a structural title keeps its form.
    second = _passage_with(us_build, 4).content
    assert "The Decalogue and the natural law" in _passage_with(us_build, 3).content
    assert "SECTION TWO\n\nTHE TEN COMMANDMENTS" in second
    # A heading the source lacks is inserted where it belongs.
    assert 'THE TEN COMMANDMENTS\n\n"Teacher, what must I do …?"\n\nTeacher, what good' in second
    assert _passage_with(us_build, 7).content.startswith("ARTICLE 5\n\nTHE FIFTH COMMANDMENT\n\n")


def test_unmatched_source_lines_are_kept_as_printed(us_build):
    content = _passage_with(us_build, 4).content
    assert "natural law.\n\nExodus 20 2-17\n\nI am the LORD your God.\n\nSECTION TWO" in content


def test_footnotes_in_metadata_not_content(us_build):
    passage = _passage_with(us_build, 2267)
    notes = passage.metadata["footnotes"]
    assert [n["n"] for n in notes] == [68]
    assert notes[0]["text"].startswith("Francis, Address")
    assert "Francis, Address" not in passage.content
    # The marker sits right after "inadmissible."
    assert passage.content[:notes[0]["at"]].endswith("inadmissible.")
    # A heading's footnote goes to the passage showing the heading.
    first = _passage_with(us_build, 1)
    epigraph = next(n for n in first.metadata["footnotes"] if n["n"] == 1)
    assert first.content[:epigraph["at"]].endswith('be saved."')


def test_footnotes_do_not_change_content(tmp_path, us_build):
    bare = json.load(open(_US, encoding="utf-8"))
    for item in bare["items"]:
        item["footnotes"] = []
    path = tmp_path / "us_no_notes.json"
    path.write_text(json.dumps(bare), encoding="utf-8")
    without = _catechism.build(_SRC, str(path)).document.passages
    with_notes = us_build.document.passages
    assert [(p.anchor, p.content) for p in without] == [(p.anchor, p.content) for p in with_notes]
    assert all(p.metadata["footnotes"] == [] for p in without)


def test_footnote_offsets_survive_split(us_build):
    pieces = [p for p in us_build.document.passages if p.metadata["ccc_paragraphs"] == [2269]]
    assert [p.anchor for p in pieces] == ["ccc/2269-p1", "ccc/2269-p2"]
    first, second = pieces
    assert [n["n"] for n in first.metadata["footnotes"]] == [70, 71]
    assert [n["n"] for n in second.metadata["footnotes"]] == [72]
    at_split = next(n for n in first.metadata["footnotes"] if n["n"] == 71)
    assert at_split["at"] == len(first.content)       # the marker at the cut stays behind
    for piece in pieces:
        for note in piece.metadata["footnotes"]:
            assert piece.content[:note["at"]].rstrip().endswith(".")


def test_every_paragraph_keeps_its_ccc_paragraphs(us_build):
    numbers = sorted(n for p in us_build.document.passages for n in p.metadata["ccc_paragraphs"])
    assert sorted(set(numbers)) == [1, 2, 3, 4, 5, 6, 7, 2267, 2268, 2269]


def test_report_reconstructs_and_classifies(us_build):
    from checks import catechism_us as report

    source = json.load(open(_SRC, encoding="utf-8"))
    result = report.report(us_build, source, None)
    assert result["reconstruction"]["in_order"]
    assert result["reconstruction"]["missing_us_items"] == []
    assert result["reconstruction"]["repeated"] == []
    assert result["footnotes"]["mismatched_numbers"] == []
    assert result["substantive"] == [2267]
    assert result["spelling_pairs"] == {"saviour -> savior": 1, "defence -> defense": 1}
    assert [x["new"] for x in result["headings"]["fuzzy"]] == ["The Decalogue and the natural law"]
    assert len(result["headings"]["unmatched_lines"]) == 2
    assert report.stops(result) == []


def _in_brief_fixture(tmp_path):
    def P(*els):
        return {"attrs": {}, "elements": list(els)}
    src = {"page_nodes": {
        "toc-1": {"paragraphs": [P({"type": "ref-ccc", "ref_number": 1}, {"type": "text", "text": "First teaching."})]},
        "toc-2": {"paragraphs": [P({"type": "text", "text": "IN BRIEF"}),
                                 P({"type": "ref-ccc", "ref_number": 2}, {"type": "text", "text": "A first summary."})]},
        "toc-3": {"paragraphs": [P({"type": "ref-ccc", "ref_number": 3}, {"type": "text", "text": "Second teaching."})]},
        "toc-4": {"paragraphs": [P({"type": "text", "text": "IN BRIEF"}),
                                 P({"type": "ref-ccc", "ref_number": 4}, {"type": "text", "text": "A second summary."})]},
    }}
    us = {"items": [
        {"kind": "paragraph", "n": 1, "text": "First teaching.", "footnotes": []},
        {"kind": "heading", "text": "IN BRIEF", "footnotes": []},
        {"kind": "paragraph", "n": 2, "text": "A first summary.", "footnotes": []},
        {"kind": "paragraph", "n": 3, "text": "Second teaching.", "footnotes": []},
        {"kind": "heading", "text": "IN BRIEF", "footnotes": []},
        {"kind": "paragraph", "n": 4, "text": "A second summary.", "footnotes": []},
    ]}
    (tmp_path / "src.json").write_text(json.dumps(src))
    (tmp_path / "us.json").write_text(json.dumps(us))
    return str(tmp_path / "src.json"), str(tmp_path / "us.json"), src


def test_live_openings_walk_forward_past_a_repeated_heading(tmp_path, monkeypatch):
    from checks import catechism_us as report

    monkeypatch.setattr(_catechism, "_MIN_CONTENT", 1)
    src_path, us_path, source = _in_brief_fixture(tmp_path)
    build = _catechism.build(src_path, us_path)
    contents = [p.content for p in build.document.passages]
    assert contents[1].startswith("IN BRIEF") and contents[3].startswith("IN BRIEF")
    live = [{"anchor": p.anchor, "position": p.position, "content": p.content}
            for p in build.document.passages]
    identity = report.openings(build, source, live)
    assert identity["opens_differently"] == [] and identity["removed"] == []
    # Moving the second summary under the first heading must be caught, which a
    # first-match lookup of "IN BRIEF" would not do.
    moved = copy.deepcopy(live)
    moved[3]["anchor"], moved[1]["anchor"] = moved[1]["anchor"], moved[3]["anchor"]
    assert report.openings(build, source, moved)["opens_differently"]


_PAGE = """
<div class="section"><div class="navigation"> <a href="#">Part 3: Life in Christ</a> (1691 - 2557)</div>
<div class="navigation"> Section 2: The Ten Commandments (2052 - 2557)</div>
<div class="heading pre">"Teacher," he said.<a href="#" id="fnref:h753:1"><SUP>1</SUP></a> Then more. <a href="#!/search/2052">&#x21E1;</a></div>
<div class="paragraph " id="para-2052"><div class="para"><div class="number"><a>2052</a></div>
<div class="text">To the young man <EM>who</EM> asked,<a href="#" id="fnref:2052:2"><SUP>2</SUP></a> Jesus answers.<P>A second part.</P></div>
<div class="footnotes"><div class="note" id="fn:2052:2"><div class="num">2.</div><div class="text"><a><I>Mt</I> 19:16</a>.</div></div>
<div class="note" id="fn:h14:1"><div class="num">1.</div><div class="text">Jn 17:3.</div></div></div></div></div>
</div>"""


def test_parse_page_reads_text_markers_and_structure():
    items, notes = parse_page(_PAGE)
    kinds = [i["kind"] for i in items]
    assert kinds == ["structure", "structure", "heading", "paragraph"]
    kept = drop_repeated_structure(items)
    # Part 3 opens at 1691, not here: a breadcrumb repeated at a page top.
    assert [i["text"] for i in kept if i["kind"] == "structure"] == ["Section 2: The Ten Commandments"]
    paragraph = items[3]
    assert paragraph["text"] == "To the young man who asked, Jesus answers.\n\nA second part."
    assert paragraph["text"][:paragraph["footnotes"][0]["at"]].endswith("asked,")
    assert items[2]["text"] == '"Teacher," he said. Then more.'
    resolved = resolve(kept, notes)
    # The heading's markers (h753) find their notes filed under another id (h14).
    assert resolved[1]["footnotes"] == [{"n": 1, "text": "Jn 17:3.", "at": 19}]
    assert resolved[2]["footnotes"][0]["text"] == "Mt 19:16."


def test_resolve_refuses_a_marker_without_a_note():
    items, notes = parse_page(_PAGE)
    del notes["h14:1"]
    with pytest.raises(ValueError, match="markers without notes"):
        resolve(drop_repeated_structure(items), notes)


def test_parse_page_refuses_unknown_markup():
    with pytest.raises(ValueError, match="unexpected <table>"):
        parse_page('<div class="paragraph " id="para-1"><div class="number">1</div>'
                   '<div class="text">x<table></table></div></div>')


def _mini(tmp_path, source_paragraphs, us_items, name="mini"):
    """Build a one-node source and its US items, numbered paragraphs given as ints."""
    def P(x):
        if isinstance(x, tuple):
            n, text = x
            return {"attrs": {}, "elements": [{"type": "ref-ccc", "ref_number": n}, {"type": "text", "text": text}]}
        return {"attrs": {}, "elements": [{"type": "text", "text": x}]}
    src = {"page_nodes": {"toc-1": {"paragraphs": [P(x) for x in source_paragraphs]}}}
    us = {"items": us_items}
    (tmp_path / f"{name}_src.json").write_text(json.dumps(src))
    (tmp_path / f"{name}_us.json").write_text(json.dumps(us))
    return _catechism.build(str(tmp_path / f"{name}_src.json"), str(tmp_path / f"{name}_us.json"))


def _para(n, text, notes=()):
    return {"kind": "paragraph", "n": n, "text": text, "footnotes": list(notes)}


def _head(text, kind="heading"):
    return {"kind": kind, "text": text, "footnotes": []}


def test_two_headings_on_one_source_line_split_at_the_dash(tmp_path):
    build = _mini(tmp_path,
                  [(1, "First teaching here."), "CHAPTER ONE",
                   "THE REVELATION OF PRAYER - THE UNIVERSAL CALL TO PRAYER", (2, "Second teaching here.")],
                  [_para(1, "First teaching here."), _head("Chapter 1: The Revelation of Prayer", "structure"),
                   _head("THE UNIVERSAL CALL TO PRAYER"), _para(2, "Second teaching here.")])
    match = next(m for m in build.alignment.matches if m.after == 1)
    assert [h.item["text"] for h in match.headings] == [
        "Chapter 1: The Revelation of Prayer", "THE UNIVERSAL CALL TO PRAYER"]
    assert not match.inserted and not match.unmatched


def test_structural_titles_match_across_level_words(tmp_path):
    # The site calls Part Four's Articles "Chapter"; the source's "Article 2" is kept.
    build = _mini(tmp_path,
                  [(1, "First teaching here."), "Article 2", '"OUR FATHER WHO ART IN HEAVEN"', (2, "Second.")],
                  [_para(1, "First teaching here."), _head('Chapter 2: "Our Father Who art in Heaven"', "structure"),
                   _para(2, "Second.")])
    assert 'First teaching here.\n\nArticle 2\n\n"OUR FATHER WHO ART IN HEAVEN"\n\nSecond.' \
        in build.document.passages[0].content
    match = next(m for m in build.alignment.matches if m.after == 1)
    assert len(match.headings) == 1 and not match.inserted


def test_a_badly_misprinted_heading_line_is_matched_by_similarity(tmp_path):
    build = _mini(tmp_path,
                  [(1, "First teaching here."), "Characteristics of the People of Got", (2, "Second.")],
                  [_para(1, "First teaching here."), _head("Characteristics of the People of God"), _para(2, "Second.")])
    match = next(m for m in build.alignment.matches if m.after == 1)
    assert [(h.item["text"], h.fuzzy) for h in match.headings] == [("Characteristics of the People of God", True)]
    text = " ".join(p.content for p in build.document.passages)
    assert "People of God" in text and "People of Got" not in text


def test_a_heading_in_mid_sentence_is_not_matched(tmp_path):
    # "the Old Testament" inside the paragraph's own sentence is not the heading.
    build = _mini(tmp_path,
                  [(1, "It includes 46 books."), "It includes 46 books for the Old Testament and 27 for the New.",
                   "The Old Testament", (2, "Second.")],
                  [_para(1, "It includes 46 books. It includes 46 books for the Old Testament and 27 for the New."),
                   _head("The Old Testament"), _para(2, "Second.")])
    match = next(m for m in build.alignment.matches if m.after == 1)
    assert match.continuation == [0] and match.unmatched == []
    assert match.toks[match.headings[0].start].line == 1


def test_a_heading_one_gap_away_is_moved_not_duplicated(tmp_path):
    build = _mini(tmp_path,
                  [(1, "First."), (2, "The doctrine of indulgences."), "What is an indulgence?",
                   '"An indulgence is a remission."', (3, "Third.")],
                  [_para(1, "First."), _head("What is an indulgence?"),
                   _para(2, 'The doctrine of indulgences. "An indulgence is a remission."'), _para(3, "Third.")])
    text = "\n\n".join(p.content for p in build.document.passages)
    assert text.count("What is an indulgence?") == 1
    assert text.index("What is an indulgence?") < text.index("The doctrine of indulgences")
    match = next(m for m in build.alignment.matches if m.after == 2)
    assert match.moved and not match.unmatched


def test_a_heading_glued_to_its_paragraph_line_is_left_out_of_the_old_text(tmp_path):
    build = _mini(tmp_path,
                  [(1, 'He made all things.  God creates "out of nothing"'), (2, "Second.")],
                  [_para(1, "He made all things."), _head('God creates "out of nothing"'), _para(2, "Second.")])
    assert build.alignment.old_paragraphs[1] == "He made all things."
    assert 'He made all things.\n\nGod creates "out of nothing"\n\nSecond.' in build.document.passages[0].content


def test_ccc_2267_declares_its_replaced_text(us_build):
    assert _passage_with(us_build, 2267).metadata["text_replaced"] == "2018 revision of CCC 2267"
    assert all("text_replaced" not in p.metadata for p in us_build.document.passages
               if 2267 not in p.metadata["ccc_paragraphs"])


def test_a_heading_only_section_carries_into_the_next_passage():
    # A large node whose last section is a bare heading: it heads the next node.
    long_text = "word " * 900
    nodes = [
        {"paragraphs": [_make_para(long_text, ref_ccc=1), _make_para("II. THE NEXT PART")]},
        {"paragraphs": [_make_para("Second teaching.", ref_ccc=2)]},
    ]
    chunks = chunk_nodes(nodes, ["toc-1", "toc-2"])
    assert chunks[-1][0].startswith("II. THE NEXT PART\n\nSecond teaching.")


def test_a_note_printed_twice_is_allowed_only_word_for_word():
    page = _PAGE.replace(
        '<div class="note" id="fn:h14:1">',
        '<div class="note" id="fn:2053:2"><div class="num">2.</div><div class="text"><a><I>Mt</I> 19:16</a>.</div></div>'
        '<div class="note" id="fn:h14:1">')
    items, notes = parse_page(page)
    resolve(drop_repeated_structure(items), notes)          # the same note again: fine
    notes["2053:2"]["text"] = "Something else."
    with pytest.raises(ValueError, match="notes without markers"):
        resolve(drop_repeated_structure(items), notes)


def test_section_two_of_part_one_is_printed_once(tmp_path):
    # toc-45 prints "SECTION TWO" with no title, then "I. THE CREEDS"; the US site has
    # the title as a breadcrumb and the heading as "THE CREEDS".
    build = _mini(tmp_path,
                  [(184, "Faith ends here."), "The Credo", "SECTION TWO", "I. THE CREEDS",
                   (185, "Whoever says I believe.")],
                  [_para(184, "Faith ends here."),
                   _head("Section 2: The Profession of the Christian Faith", "structure"),
                   _head("THE CREEDS"), _para(185, "Whoever says I believe.")])
    text = "\n\n".join(p.content for p in build.document.passages)
    assert text.count("SECTION TWO") == 1 and text.count("THE CREEDS") == 1
    assert "The Credo\n\nSECTION TWO\n\nTHE PROFESSION OF THE CHRISTIAN FAITH\n\nI. THE CREEDS\n\nWhoever" in text
    match = next(m for m in build.alignment.matches if m.after == 184)
    assert not match.inserted
    assert [match.lines[i].text for i in match.unmatched] == ["The Credo"]


def _us_doc():
    return {"items": [
        {"kind": "paragraph", "n": 1, "text": "He said \"come\", and went.", "footnotes": [{"n": 5, "text": "Mt 1:1.", "at": 15}]},
        {"kind": "heading", "text": "A Heading", "footnotes": [{"n": 6, "text": "Old note.", "at": 9}]},
        {"kind": "paragraph", "n": 2, "text": "First words, then more words.", "footnotes": [
            {"n": 7, "text": "Wrong.", "at": 12}, {"n": 8, "text": "Wronger.", "at": 29}]},
    ]}


def test_a_correction_moves_the_footnotes_after_it():
    us = _cu.apply_corrections(_us_doc(), [{"n": 1, "find": "\"come\",", "replace": "\"come,\""}])
    item = us["items"][0]
    assert item["text"] == "He said \"come,\" and went."
    assert item["footnotes"][0]["at"] == 15 and item["_fetched_text"].startswith("He said \"come\",")


def test_a_correction_that_does_not_occur_once_fails():
    with pytest.raises(ValueError, match="occurs 0 times"):
        _cu.apply_corrections(_us_doc(), [{"n": 1, "find": "absent", "replace": "x"}])


def test_footnote_corrections_replace_a_note_and_a_paragraphs_notes():
    us = _cu.apply_footnote_corrections(
        _us_doc(),
        [{"n": 1, "note": 5, "text": "Mt 1:2."}, {"heading": "A Heading", "note": 6, "text": "New note."}],
        [{"n": 2, "notes": [{"n": 10, "after": "more words.", "text": "B."}, {"n": 9, "after": "First words,", "text": "A."}]}])
    assert us["items"][0]["footnotes"][0]["text"] == "Mt 1:2."
    assert us["items"][1]["footnotes"][0]["text"] == "New note."
    assert us["items"][2]["footnotes"] == [{"n": 9, "text": "A.", "at": 12}, {"n": 10, "text": "B.", "at": 29}]


def test_footnote_corrections_that_do_not_apply_fail():
    with pytest.raises(ValueError, match="note 99: found 0"):
        _cu.apply_footnote_corrections(_us_doc(), [{"n": 1, "note": 99, "text": "x"}], [])
    with pytest.raises(ValueError, match="occurs 0 times"):
        _cu.apply_footnote_corrections(_us_doc(), [], [{"n": 2, "notes": [{"n": 9, "after": "nowhere", "text": "x"}]}])


@pytest.mark.skipif(not os.path.exists(_cu.US_SOURCE), reason="vendored US edition not present")
def test_the_vendored_corrections_all_apply():
    us = _cu.load_us()           # raises if any text or footnote correction does not apply
    paragraphs = {i["n"]: i for i in us["items"] if i["kind"] == "paragraph"}
    assert "formulation she cooperates" in paragraphs[501]["text"]
    assert [(f["n"], f["text"]) for f in paragraphs[1065]["footnotes"]] == [
        (650, "Rev 3:14."), (651, "2 Cor 1:20."), (652, "Roman Missal, EP I, 98.")]
    for item in paragraphs.values():
        for note in item["footnotes"]:
            assert 0 < note["at"] <= len(item["text"])


@pytest.mark.parametrize("find,replace,at,want", [
    ("'came from God', 'descended", "\"came from God,\" \"descended", 16, 16),   # after ,"
    ("Holy Spirit\" Before", "Holy Spirit.\" Before", 12, 13),                   # after ."
    ("social action and", "social action, and", 13, 14),                         # after the new comma
    ("then \"I AM\".", "then 'I Am.'\"", 4, 4),                                   # before the words: unmoved
])
def test_a_marker_inside_corrected_words_keeps_its_place(find, replace, at, want):
    assert _cu._move_offset(at, 0, find, replace) == want
