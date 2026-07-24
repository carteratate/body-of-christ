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
from scripts.pass1_pilot_diff_report import (
    _content_words, jaccard, distribution, FacetRecord, CollectionStats,
    _generate_with_instrumentation, build_report, run,
)


# --- pure helpers ---

def test_content_words_strips_stopwords_and_short_words():
    words = _content_words("The Word was with God and was God")
    assert "the" not in words and "was" not in words and "and" not in words
    assert "word" in words and "god" in words


def test_jaccard_identical_sets():
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint_sets():
    assert jaccard({"a"}, {"b"}) == 0.0


def test_jaccard_both_empty():
    assert jaccard(set(), set()) == 0.0


def test_distribution_empty():
    assert distribution([]) == {"n": 0}


def test_distribution_basic():
    d = distribution([1, 2, 3, 4, 5])
    assert d["n"] == 5
    assert d["min"] == 1 and d["max"] == 5
    assert d["median"] == 3


# --- _generate_with_instrumentation ---

def _good_facet(tag="0"):
    return {
        "text": f"Raw working treatment {tag} with extra detail for testing purposes today.",
        "takeaway": (
            f"This passage establishes David's kingship through a theological claim "
            f"labeled {tag} that remains distinct from any other reading, grounded "
            f"firmly in the surrounding narrative context and consistent with sound "
            f"doctrine throughout."
        ),
        "question": f"q{tag}",
    }


def _bad_facet(tag="0"):
    return {"text": "short working text", "takeaway": "Too short.", "question": f"q{tag}"}


class _AlwaysGoodClient:
    def __init__(self):
        self.calls = 0

    async def generate(self, system, context, temperature=None, retry_errors=None):
        self.calls += 1
        from enrichment.schema import GenerationOutput
        from enrichment.client import Usage
        return GenerationOutput.model_validate(
            {"facets": [_good_facet("0"), _good_facet("1")]}), Usage(10, 5)

    async def close(self):
        pass


class _BadThenGoodClient:
    def __init__(self):
        self.calls = 0

    async def generate(self, system, context, temperature=None, retry_errors=None):
        self.calls += 1
        from enrichment.schema import GenerationOutput
        from enrichment.client import Usage
        if retry_errors is None:
            return GenerationOutput.model_validate(
                {"facets": [_bad_facet("0"), _good_facet("1")]}), Usage(10, 5)
        return GenerationOutput.model_validate(
            {"facets": [_good_facet("0"), _good_facet("1")]}), Usage(10, 5)


class _AlwaysBadClient:
    def __init__(self):
        self.calls = 0

    async def generate(self, system, context, temperature=None, retry_errors=None):
        self.calls += 1
        from enrichment.schema import GenerationOutput
        from enrichment.client import Usage
        return GenerationOutput.model_validate(
            {"facets": [_bad_facet("0"), _good_facet("1")]}), Usage(10, 5)


PASSAGE_CONTENT = "some passage content for testing"


@pytest.mark.asyncio
async def test_instrumentation_no_retry_when_all_good():
    client = _AlwaysGoodClient()
    final, first_failures, retried, retry_ok, count = await _generate_with_instrumentation(
        client, "sys", "ctx", PASSAGE_CONTENT)
    assert final is not None
    assert first_failures == {}
    assert retried is False
    assert retry_ok is None
    assert count == 2
    assert client.calls == 1


@pytest.mark.asyncio
async def test_instrumentation_retries_and_succeeds():
    client = _BadThenGoodClient()
    final, first_failures, retried, retry_ok, count = await _generate_with_instrumentation(
        client, "sys", "ctx", PASSAGE_CONTENT)
    assert final is not None
    assert 0 in first_failures
    assert retried is True
    assert retry_ok is True
    assert count == 2
    assert client.calls == 2


@pytest.mark.asyncio
async def test_instrumentation_retries_and_still_fails():
    client = _AlwaysBadClient()
    final, first_failures, retried, retry_ok, count = await _generate_with_instrumentation(
        client, "sys", "ctx", PASSAGE_CONTENT)
    assert final is None
    assert 0 in first_failures
    assert retried is True
    assert retry_ok is False
    assert client.calls == 2


# --- build_report ---

def test_build_report_includes_collection_and_metrics():
    stats = CollectionStats(facets_checked=10, chunks_needing_retry=2, chunks_retry_succeeded=1,
                            chunks_hard_failed=1)
    stats.check_failure_counts["word_count"] = 3
    records = [FacetRecord(collection="bible", anchor="a1", text="working text here",
                          takeaway="This passage establishes David's point clearly and firmly.",
                          question="What does this teach?")]
    report = build_report({"bible": stats}, records)
    assert "bible" in report
    assert "word_count" in report
    assert "anti-copy" in report.lower() or "anti_copy" in report.lower()
    assert "David's point" in report  # random-sample dump includes the takeaway


def test_build_report_handles_no_facet_records():
    report = build_report({"bible": CollectionStats()}, [])
    assert "bible" in report


# --- end-to-end with a stub client ---

@pytest.mark.asyncio
async def test_run_end_to_end_against_single_mocked_chunk(tmp_path, monkeypatch):
    p = Passage(content="In the beginning God created the heavens and the earth.",
               reference="Gen 1:1", anchor="genesis/1/1", chapter_key="genesis/1",
               chapter_label="Genesis 1", position=0)
    doc = Document(id="d1", collection="bible", title="Genesis", author="Moses", passages=[p])

    monkeypatch.setattr("stages.parse.parse", lambda collection: [doc])
    monkeypatch.setattr(
        "enrichment.client.EnrichmentClient",
        lambda api_key, model, concurrency: _AlwaysGoodClient(),
    )

    csv_path = tmp_path / "chunks.csv"
    csv_path.write_text("collection,anchor\nbible,genesis/1/1\n")
    out_path = tmp_path / "report.txt"

    written_to = await run(str(csv_path), str(out_path))
    assert written_to == str(out_path)
    content = out_path.read_text()
    assert "PASS 1 TAKEAWAY PILOT DIFF REPORT" in content
    assert "bible" in content
