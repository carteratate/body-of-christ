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
