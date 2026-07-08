# datapipeline/tests/test_enrichment_schema.py
import pytest
from pydantic import ValidationError
from enrichment.schema import (
    GenerationOutput, ClassificationOutput, MergedEnrichment,
    CONFIDENCE_VALUES, KIND_VALUES,
    generation_tool_schema, classification_tool_schema,
)


def test_generation_output_parses():
    g = GenerationOutput.model_validate(
        {"facets": [{"text": "t", "question": "q"}], "annotation": "SUMMARY: x"})
    assert g.facets[0].text == "t"


def test_classification_rejects_bad_kind():
    with pytest.raises(ValidationError):
        ClassificationOutput.model_validate({"labels": [{"confidence": "explicit", "kind": "nope"}]})


def test_taxonomy_values():
    assert CONFIDENCE_VALUES == ("explicit", "traditional", "inferential")
    assert "typological" in KIND_VALUES and len(KIND_VALUES) == 7


def test_tool_schemas_are_dicts_with_properties():
    gs = generation_tool_schema()
    cs = classification_tool_schema()
    assert gs["type"] == "object" and "facets" in gs["properties"]
    assert cs["type"] == "object" and "labels" in cs["properties"]


def test_merged_enrichment_roundtrip():
    m = MergedEnrichment.model_validate({
        "facets": [{"confidence": "traditional", "kind": "typological",
                    "text": "t", "question": "q"}],
        "annotation": "SUMMARY: x"})
    assert m.facets[0].kind == "typological"
    assert m.model_dump()["facets"][0]["confidence"] == "traditional"
