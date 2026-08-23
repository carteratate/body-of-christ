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
