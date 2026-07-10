# datapipeline/tests/test_enrichment_schema.py
import pytest
from pydantic import ValidationError
from enrichment.schema import (
    GenFacet, GenerationOutput, ClassificationOutput, AnnotationOutput, MergedEnrichment,
    GROUNDING_VALUES, KIND_VALUES,
    generation_tool_schema, classification_tool_schema, annotation_tool_schema,
)


def test_generation_output_parses_without_annotation():
    g = GenerationOutput.model_validate(
        {"facets": [{"text": "t", "takeaway": "tk", "question": "q"}]})
    assert g.facets[0].text == "t"
    assert g.facets[0].takeaway == "tk"
    assert not hasattr(g, "annotation")


def test_gen_facet_requires_takeaway():
    with pytest.raises(ValidationError):
        GenerationOutput.model_validate({"facets": [{"text": "t", "question": "q"}]})


def test_gen_facet_field_order_is_text_takeaway_question():
    # Field order matters: the tool schema's declared property order must match
    # text -> takeaway -> question, since the takeaway is meant to be generated
    # conditioned on the text (per the prompt's instructions).
    assert list(GenFacet.model_fields) == ["text", "takeaway", "question"]


def test_generation_tool_schema_facet_property_order():
    gs = generation_tool_schema()
    facet_schema = gs["$defs"]["GenFacet"]
    assert list(facet_schema["properties"]) == ["text", "takeaway", "question"]


def test_classification_rejects_bad_kind():
    with pytest.raises(ValidationError):
        ClassificationOutput.model_validate(
            {"labels": [{"grounding": "explicit", "evidence": "x", "kind": "nope"}]})


def test_classification_rejects_bad_grounding():
    with pytest.raises(ValidationError):
        ClassificationOutput.model_validate(
            {"labels": [{"grounding": "traditional", "evidence": "x", "kind": "doctrinal"}]})


def test_classification_label_kind_secondary_optional():
    c = ClassificationOutput.model_validate(
        {"labels": [{"grounding": "explicit", "evidence": "x", "kind": "doctrinal"}]})
    assert c.labels[0].kind_secondary is None


def test_classification_label_kind_secondary_accepted():
    c = ClassificationOutput.model_validate(
        {"labels": [{"grounding": "settled", "evidence": "x", "kind": "typological",
                    "kind_secondary": "devotional"}]})
    assert c.labels[0].kind_secondary == "devotional"


def test_taxonomy_values():
    assert GROUNDING_VALUES == ("explicit", "settled", "inferential")
    assert "typological" in KIND_VALUES and len(KIND_VALUES) == 7


def test_tool_schemas_are_dicts_with_properties():
    gs = generation_tool_schema()
    cs = classification_tool_schema()
    ans = annotation_tool_schema()
    assert gs["type"] == "object" and "facets" in gs["properties"]
    assert "annotation" not in gs["properties"]
    assert cs["type"] == "object" and "labels" in cs["properties"]
    assert ans["type"] == "object" and "annotation" in ans["properties"]


def test_annotation_output_parses():
    a = AnnotationOutput.model_validate({"annotation": "SUMMARY: x"})
    assert a.annotation == "SUMMARY: x"


def test_merged_enrichment_roundtrip():
    m = MergedEnrichment.model_validate({
        "facets": [{"grounding": "settled", "evidence": "x", "kind": "typological",
                    "kind_secondary": None, "text": "t", "question": "q"}],
        "annotation": "SUMMARY: x"})
    assert m.facets[0].kind == "typological"
    assert m.model_dump()["facets"][0]["grounding"] == "settled"


def test_merged_facet_kind_secondary_defaults_to_none():
    m = MergedEnrichment.model_validate({
        "facets": [{"grounding": "explicit", "evidence": "x", "kind": "doctrinal",
                    "text": "t", "question": "q"}],
        "annotation": "SUMMARY: x"})
    assert m.facets[0].kind_secondary is None


def test_merged_facet_working_text_defaults_to_none():
    m = MergedEnrichment.model_validate({
        "facets": [{"grounding": "explicit", "evidence": "x", "kind": "doctrinal",
                    "text": "t", "question": "q"}],
        "annotation": "SUMMARY: x"})
    assert m.facets[0].working_text is None


def test_merged_facet_working_text_accepted_when_present():
    m = MergedEnrichment.model_validate({
        "facets": [{"grounding": "explicit", "evidence": "x", "kind": "doctrinal",
                    "text": "t", "question": "q", "working_text": "the raw working treatment"}],
        "annotation": "SUMMARY: x"})
    assert m.facets[0].working_text == "the raw working treatment"
