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
from scripts.pass1_questions_cosine_audit import (
    cosine_similarity, percentile, QuestionTakeawayPair, build_report, embed_all, run,
)


# --- pure helpers ---

def test_cosine_similarity_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector_is_zero_not_error():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_percentile_median():
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3


def test_percentile_empty_is_nan():
    import math
    assert math.isnan(percentile([], 0.5))


@pytest.mark.asyncio
async def test_embed_all_batches_requests():
    calls = []

    class _StubEmbed:
        async def embed(self, texts):
            calls.append(list(texts))
            return [[float(len(t))] for t in texts]

    vectors = await embed_all(_StubEmbed(), ["a", "bb", "ccc", "dddd", "e"], batch_size=2)
    assert len(vectors) == 5
    assert len(calls) == 3  # batches of 2, 2, 1


# --- build_report ---

def test_build_report_includes_overall_and_per_collection():
    pairs = [
        QuestionTakeawayPair(collection="bible", anchor="a1", question="q1",
                             takeaway="t1", cosine=0.8),
        QuestionTakeawayPair(collection="bible", anchor="a2", question="q2",
                             takeaway="t2", cosine=0.6),
        QuestionTakeawayPair(collection="catechism", anchor="c1", question="q3",
                             takeaway="t3", cosine=0.9),
    ]
    report = build_report(pairs)
    assert "OVERALL" in report
    assert "bible" in report and "catechism" in report
    assert "does not decide" in report


def test_build_report_handles_no_pairs():
    report = build_report([])
    assert "no pairs" in report


# --- end-to-end with a stub client ---

class _StubGenClient:
    def __init__(self):
        self.calls = 0

    async def generate(self, system, context, temperature=None, retry_errors=None,
                       thinking=False, effort=None):
        self.calls += 1
        from enrichment.schema import GenerationOutput
        from enrichment.client import Usage
        return GenerationOutput.model_validate(
            {"facets": [
                {"text": "raw working text for facet zero, more detail here for testing.",
                 "takeaway": ("This passage establishes David's kingship through a theological "
                             "claim labeled zero that remains distinct from any other reading, "
                             "grounded firmly in the surrounding narrative context and "
                             "consistent with sound doctrine throughout."),
                 "question": "What does this teach about David's kingship?"},
            ]}
        ), Usage(10, 5)

    async def close(self):
        pass


class _StubEmbedClient:
    def __init__(self):
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        return [[float(len(t)), 1.0] for t in texts]

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_run_end_to_end_against_single_mocked_chunk(tmp_path, monkeypatch):
    p = Passage(content="In the beginning God created the heavens and the earth.",
               reference="Gen 1:1", anchor="genesis/1/1", chapter_key="genesis/1",
               chapter_label="Genesis 1", position=0)
    doc = Document(id="d1", collection="bible", title="Genesis", author="Moses", passages=[p])

    monkeypatch.setattr("stages.parse.parse", lambda collection: [doc])
    monkeypatch.setattr(
        "enrichment.client.EnrichmentClient",
        lambda api_key, model, concurrency: _StubGenClient(),
    )
    monkeypatch.setattr(
        "embeddings.EmbeddingClient",
        lambda api_key, model: _StubEmbedClient(),
    )

    csv_path = tmp_path / "chunks.csv"
    csv_path.write_text("collection,anchor\nbible,genesis/1/1\n")
    out_path = tmp_path / "report.txt"

    written_to = await run(str(csv_path), str(out_path))
    assert written_to == str(out_path)
    content = out_path.read_text()
    assert "QUESTIONS-INDEX COSINE AUDIT" in content
    assert "bible" in content
