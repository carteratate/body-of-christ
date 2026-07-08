import os

# config.py constructs its module-level singleton at import time via
# _require_env(), which raises if these vars are absent. The real
# datapipeline/.env does not define QDRANT_URL/QDRANT_API_KEY, so we need
# placeholders present before the first `import config` in this process.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

import pytest
from enrichment.schema import GenerationOutput, ClassificationOutput
from enrichment.merge import merge, MergeError


def _gen(n):
    return GenerationOutput.model_validate(
        {"facets": [{"text": f"t{i}", "question": f"q{i}"} for i in range(n)],
         "annotation": "SUMMARY: x"})


def _cls(kinds):
    return ClassificationOutput.model_validate(
        {"labels": [{"confidence": "explicit", "kind": k} for k in kinds]})


def test_merge_zips_parallel_arrays():
    m = merge(_gen(2), _cls(["doctrinal", "typological"]))
    assert [f.kind for f in m.facets] == ["doctrinal", "typological"]
    assert m.facets[0].text == "t0" and m.facets[1].question == "q1"
    assert m.annotation == "SUMMARY: x"


def test_merge_length_mismatch_raises():
    with pytest.raises(MergeError):
        merge(_gen(3), _cls(["doctrinal", "typological"]))


def test_merge_too_few_facets_raises():
    with pytest.raises(MergeError):
        merge(_gen(1), _cls(["doctrinal"]))


def test_merge_too_many_facets_raises():
    with pytest.raises(MergeError):
        merge(_gen(13), _cls(["doctrinal"] * 13))
