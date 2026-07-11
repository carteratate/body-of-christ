import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from model import Document, Passage
from enrichment.client import Usage
from scripts.enrichment_sample_run import (
    read_chunk_list, group_by_collection, format_facet, format_chunk_report,
    build_summary_table, run,
)
from enrichment.schema import MergedEnrichment


# --- read_chunk_list ---

def test_read_chunk_list_parses_rows(tmp_path):
    p = tmp_path / "chunks.csv"
    p.write_text("bible,genesis/3/1\ncatechism,ccc/2/1/1/1\n")
    rows = read_chunk_list(str(p))
    assert rows == [("bible", "genesis/3/1"), ("catechism", "ccc/2/1/1/1")]


def test_read_chunk_list_skips_header_row(tmp_path):
    p = tmp_path / "chunks.csv"
    p.write_text("collection,anchor\nbible,genesis/3/1\n")
    rows = read_chunk_list(str(p))
    assert rows == [("bible", "genesis/3/1")]


def test_read_chunk_list_skips_blank_lines(tmp_path):
    p = tmp_path / "chunks.csv"
    p.write_text("bible,genesis/3/1\n\ncatechism,ccc/2/1/1/1\n")
    rows = read_chunk_list(str(p))
    assert len(rows) == 2


def test_read_chunk_list_rejects_short_rows(tmp_path):
    p = tmp_path / "chunks.csv"
    p.write_text("bible\n")
    with pytest.raises(ValueError):
        read_chunk_list(str(p))


# --- group_by_collection ---

def test_group_by_collection():
    rows = [("bible", "a1"), ("bible", "a2"), ("catechism", "c1")]
    grouped = group_by_collection(rows)
    assert grouped == {"bible": ["a1", "a2"], "catechism": ["c1"]}


# --- formatting ---

def _merged():
    return MergedEnrichment.model_validate({
        "facets": [
            {"grounding": "explicit", "evidence": "quoted words", "kind": "doctrinal",
             "text": "t0", "question": "q0"},
            {"grounding": "settled", "evidence": "e1", "kind": "moral",
             "kind_secondary": "devotional", "text": "t1", "question": "q1"},
        ],
        "annotation": "SUMMARY: s\n\n[DOCTRINAL | explicit]: a\n[MORAL/DEVOTIONAL | settled]: b",
    })


def test_format_facet_shows_secondary_kind():
    merged = _merged()
    out = format_facet(2, merged.facets[1])
    assert "moral/devotional | settled" in out
    assert "e1" in out


def test_format_chunk_report_includes_content_facets_and_annotation():
    p = Passage(content="In the beginning", reference="Gen 1:1", anchor="genesis/1/1",
                chapter_key="genesis/1", chapter_label="Genesis 1", position=0)
    out = format_chunk_report("bible", "genesis/1/1", p, merged=_merged())
    assert "Gen 1:1" in out
    assert "In the beginning" in out
    assert "doctrinal | explicit" in out
    assert "SUMMARY: s" in out


def test_format_chunk_report_shows_error_when_present():
    p = Passage(content="x", reference="r", anchor="a", chapter_key="k",
                chapter_label="l", position=0)
    out = format_chunk_report("bible", "a", p, error="label count mismatch")
    assert "VALIDATION FAILED" in out
    assert "label count mismatch" in out


def test_format_chunk_report_handles_missing_chunk():
    out = format_chunk_report("bible", "nonexistent", None, error="no chunk found")
    assert "no chunk found" in out


def test_format_chunk_report_includes_warnings_when_present():
    p = Passage(content="x", reference="r", anchor="a", chapter_key="k",
                chapter_label="l", position=0)
    out = format_chunk_report("bible", "a", p, merged=_merged(), warnings=["annotation is ~10 tokens"])
    assert "WARNINGS:" in out
    assert "annotation is ~10 tokens" in out


# --- build_summary_table ---

def test_summary_table_reports_counts_and_distributions():
    results = {"bible": [_merged(), _merged()]}
    failures = {"bible": 1}
    warning_counts = {"bible": 2}
    table = build_summary_table(results, failures, warning_counts)
    assert "bible" in table
    # 2 chunks x 2 facets = 4 facets total; 2 explicit, 2 settled, 0 inferential
    assert "2/2/0" in table
    # each chunk contributes one facet with a secondary kind -> 2 total
    assert "kind distribution" in table


def test_summary_table_includes_collections_with_only_failures():
    results = {}
    failures = {"canon-law": 3}
    warning_counts = {}
    table = build_summary_table(results, failures, warning_counts)
    assert "canon-law" in table


# --- end-to-end with a single mocked/stubbed chunk (acceptance criterion) ---

def _valid_facet_dict(tag):
    """A GenFacet dict that passes validate_generation()'s hard checks (mirrors
    the helper in tests/test_stage_enrich.py)."""
    return {
        "text": f"This is the raw working treatment for facet {tag}, written out in "
                f"full theological detail for the purposes of this test.",
        "takeaway": (
            f"This passage establishes David's kingship through a theological claim "
            f"labeled {tag} that remains distinct from any other reading, grounded "
            f"firmly in the surrounding narrative context and consistent with sound "
            f"doctrine throughout."
        ),
        "question": f"q{tag}",
    }


class _StubGenClient:
    async def generate(self, system, context, retry_errors=None):
        from enrichment.schema import GenerationOutput
        return GenerationOutput.model_validate(
            {"facets": [_valid_facet_dict("0"), _valid_facet_dict("1")]}
        ), Usage(10, 5)

    async def close(self):
        pass


class _StubClassifyClient:
    async def classify(self, system, context, facets, retry_errors=None):
        from enrichment.schema import ClassificationOutput
        return ClassificationOutput.model_validate(
            {"labels": [{"grounding": "settled", "evidence": "e0", "kind": "doctrinal"},
                       {"grounding": "settled", "evidence": "e1", "kind": "typological"}]}
        ), Usage(8, 3)

    async def assemble_annotation(self, system, context, facets_with_labels, retry_errors=None):
        from enrichment.schema import AnnotationOutput
        segments = "\n".join(
            f"[{f['kind'].upper()} | {f['grounding']}]: text {i}"
            for i, f in enumerate(facets_with_labels)
        )
        return AnnotationOutput.model_validate(
            {"annotation": f"SUMMARY: overview.\n\n{segments}"}
        ), Usage(6, 4)

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_run_end_to_end_against_single_mocked_chunk(tmp_path, monkeypatch):
    p = Passage(content="In the beginning God created the heavens and the earth.",
                reference="Gen 1:1", anchor="genesis/1/1", chapter_key="genesis/1",
                chapter_label="Genesis 1", position=0)
    doc = Document(id="d1", collection="bible", title="Genesis", author="Moses", passages=[p])

    def fake_parse(collection):
        assert collection == "bible"
        return [doc]

    monkeypatch.setattr("stages.parse.parse", fake_parse)
    monkeypatch.setattr(
        "enrichment.client.EnrichmentClient",
        lambda api_key, model, concurrency: (
            _StubGenClient() if model == "claude-opus-4-8" else _StubClassifyClient()
        ),
    )

    csv_path = tmp_path / "chunks.csv"
    csv_path.write_text("collection,anchor\nbible,genesis/1/1\n")
    out_path = tmp_path / "review.txt"

    written_to = await run(str(csv_path), str(out_path))

    assert written_to == str(out_path)
    content = out_path.read_text()
    assert "Gen 1:1" in content
    assert "doctrinal | settled" in content
    assert "SUMMARY: overview." in content
    assert "SUMMARY" in content  # the trailing summary-table heading
    assert "bible" in content


@pytest.mark.asyncio
async def test_run_isolates_failures_and_continues(tmp_path, monkeypatch):
    p1 = Passage(content="good chunk", reference="Gen 1:1", anchor="genesis/1/1",
                chapter_key="genesis/1", chapter_label="Genesis 1", position=0)
    doc = Document(id="d1", collection="bible", title="Genesis", author="Moses", passages=[p1])

    monkeypatch.setattr("stages.parse.parse", lambda collection: [doc])
    monkeypatch.setattr(
        "enrichment.client.EnrichmentClient",
        lambda api_key, model, concurrency: (
            _StubGenClient() if model == "claude-opus-4-8" else _StubClassifyClient()
        ),
    )

    csv_path = tmp_path / "chunks.csv"
    # second row references an anchor that doesn't exist in the parsed doc
    csv_path.write_text("bible,genesis/1/1\nbible,genesis/1/999\n")
    out_path = tmp_path / "review.txt"

    written_to = await run(str(csv_path), str(out_path))
    content = out_path.read_text()
    assert "no chunk found" in content
    assert "genesis/1/999" in content
    # the good chunk still produced a full report
    assert "SUMMARY: overview." in content
