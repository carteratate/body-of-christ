import asyncio
import json
import os
import pytest
from stages import bm25_content_fit, bm25_annotation_fit


@pytest.mark.smoke
def test_content_fit_writes_loadable_model(tmp_path):
    out = str(tmp_path / "content.bin")
    bm25_content_fit.fit(["the eucharist", "transubstantiation of the sacrament"] * 20, out)
    assert os.path.exists(out)

    # Outcome (B): fastembed's Qdrant/bm25 model has no corpus-relative IDF fit step
    # (see docs/superpowers/plans/notes/2026-07-07-bm25-fastembed-findings.md), so
    # fit() persists a JSON config rather than a pickled model. Confirm the file is
    # a loadable config and that config reconstructs a working SparseTextEmbedding.
    with open(out) as f:
        config = json.load(f)
    assert config["model_name"] == "Qdrant/bm25"

    from fastembed import SparseTextEmbedding
    model = SparseTextEmbedding(model_name=config["model_name"],
                                 **{k: v for k, v in config.items() if k != "model_name"})
    vec = next(iter(model.embed(["a test query"])))
    assert len(vec.indices) > 0


def test_annotation_corpus_uses_prose(monkeypatch):
    # annotation prose stripping is applied to the loaded corpus
    from stages.enrich_io import annotation_prose
    raw = "SUMMARY: s\n\n[DOCTRINAL | explicit]: body"
    assert "body" in annotation_prose(raw) and "[" not in annotation_prose(raw)


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *args):
        return self._rows


def test_load_annotation_corpus_decodes_jsonb_round_trip():
    # Simulate exactly what asyncpg 0.31.0 hands back for a jsonb column: since no
    # set_type_codec is registered anywhere in this codebase, asyncpg returns the raw
    # JSON-encoded text (surrounding quotes, escaped quotes, literal \n sequences) as a
    # plain str, not the original prose. load_annotation_corpus must json.loads() it
    # before stripping the [KIND | grounding]: labels via annotation_prose().
    from stages.enrich_io import annotation_prose

    raw_prose = "SUMMARY: test\n\n[DOCTRINAL | explicit]: body"
    jsonb_as_returned_by_asyncpg = json.dumps(raw_prose)
    conn = _FakeConn([{"annotation": jsonb_as_returned_by_asyncpg}])

    corpus = asyncio.run(bm25_annotation_fit.load_annotation_corpus(conn))

    assert corpus == [annotation_prose(raw_prose)]
    result = corpus[0]
    assert result.startswith('"') is False
    assert "\\n" not in result
    assert "[DOCTRINAL | explicit]:" not in result
    assert "body" in result
