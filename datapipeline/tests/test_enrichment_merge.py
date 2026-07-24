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
from enrichment.schema import GenFacet, ClassificationOutput, identify_facets
from enrichment.merge import merge, MergeError


def _identified(n):
    facets = [GenFacet(text=f"working{i}", takeaway=f"t{i}", question=f"q{i}") for i in range(n)]
    return identify_facets(facets)


def _cls(kinds, grounding="explicit"):
    return ClassificationOutput.model_validate(
        {"labels": [{"facet_id": f"f{i + 1}", "grounding": grounding, "evidence": f"e{i}", "kind": k}
                    for i, k in enumerate(kinds)]})


def test_merge_zips_parallel_arrays():
    m = merge(_identified(2), _cls(["doctrinal", "typological"]), "SUMMARY: x")
    assert [f.kind for f in m.facets] == ["doctrinal", "typological"]
    assert m.facets[0].text == "t0" and m.facets[1].question == "q1"
    assert m.annotation == "SUMMARY: x"


def test_merge_carries_facet_id():
    m = merge(_identified(2), _cls(["doctrinal", "typological"]), "SUMMARY: x")
    assert [f.id for f in m.facets] == ["f1", "f2"]


def test_merge_text_is_the_takeaway_not_the_working_text():
    m = merge(_identified(2), _cls(["doctrinal", "typological"]), "SUMMARY: x")
    assert m.facets[0].text == "t0"          # the takeaway
    assert m.facets[0].working_text == "working0"  # Pass 1's raw working treatment


def test_merge_carries_grounding_and_evidence():
    m = merge(_identified(2), _cls(["doctrinal", "moral"], grounding="settled"), "SUMMARY: x")
    assert m.facets[0].grounding == "settled"
    assert m.facets[0].evidence == "e0"


def test_merge_carries_kind_secondary_when_present():
    cls = ClassificationOutput.model_validate(
        {"labels": [{"facet_id": "f1", "grounding": "explicit", "evidence": "e0", "kind": "doctrinal",
                     "kind_secondary": "moral"},
                    {"facet_id": "f2", "grounding": "explicit", "evidence": "e1", "kind": "moral"}]})
    m = merge(_identified(2), cls, "SUMMARY: x")
    assert m.facets[0].kind_secondary == "moral"


def test_merge_kind_secondary_defaults_to_none():
    m = merge(_identified(2), _cls(["doctrinal", "moral"]), "SUMMARY: x")
    assert m.facets[0].kind_secondary is None


def test_merge_length_mismatch_raises():
    with pytest.raises(MergeError):
        merge(_identified(3), _cls(["doctrinal", "typological"]), "SUMMARY: x")


def test_merge_too_few_facets_raises():
    with pytest.raises(MergeError):
        merge(_identified(1), _cls(["doctrinal"]), "SUMMARY: x")


def test_merge_too_many_facets_raises():
    with pytest.raises(MergeError):
        merge(_identified(13), _cls(["doctrinal"] * 13), "SUMMARY: x")
