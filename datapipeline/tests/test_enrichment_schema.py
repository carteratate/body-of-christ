# datapipeline/tests/test_enrichment_schema.py
import pytest
from pydantic import ValidationError
from enrichment.schema import (
    GenFacet, GenerationOutput, IdentifiedFacet, ClassificationOutput, AnnotationOutput,
    MergedEnrichment, GROUNDING_VALUES, KIND_VALUES, identify_facets,
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


# --- identify_facets(): stable, deterministic facet ids ---

def test_identify_facets_assigns_sequential_ids_from_position():
    facets = [GenFacet(text=f"t{i}", takeaway=f"tk{i}", question=f"q{i}") for i in range(3)]
    identified = identify_facets(facets)
    assert [f.id for f in identified] == ["f1", "f2", "f3"]
    assert [f.text for f in identified] == ["t0", "t1", "t2"]
    assert [f.takeaway for f in identified] == ["tk0", "tk1", "tk2"]
    assert [f.question for f in identified] == ["q0", "q1", "q2"]


def test_identify_facets_is_deterministic_across_calls():
    facets = [GenFacet(text="t", takeaway="tk", question="q") for _ in range(5)]
    ids_first = [f.id for f in identify_facets(facets)]
    ids_second = [f.id for f in identify_facets(facets)]
    assert ids_first == ids_second == ["f1", "f2", "f3", "f4", "f5"]


def test_identify_facets_empty_list():
    assert identify_facets([]) == []


def test_identified_facet_requires_all_fields():
    with pytest.raises(ValidationError):
        IdentifiedFacet(id="f1", text="t", takeaway="tk")  # missing question


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
        {"labels": [{"facet_id": "f1", "grounding": "explicit", "evidence": "x", "kind": "doctrinal"}]})
    assert c.labels[0].kind_secondary is None


def test_classification_label_kind_secondary_accepted():
    c = ClassificationOutput.model_validate(
        {"labels": [{"facet_id": "f1", "grounding": "settled", "evidence": "x", "kind": "typological",
                    "kind_secondary": "devotional"}]})
    assert c.labels[0].kind_secondary == "devotional"


def test_taxonomy_values():
    assert GROUNDING_VALUES == ("explicit", "settled", "inferential")
    assert "typological" in KIND_VALUES and len(KIND_VALUES) == 8
    assert "juridical" in KIND_VALUES


def test_classification_accepts_juridical_kind():
    c = ClassificationOutput.model_validate(
        {"labels": [{"facet_id": "f1", "grounding": "explicit", "evidence": "x", "kind": "juridical"}]})
    assert c.labels[0].kind == "juridical"


def test_label_requires_facet_id():
    with pytest.raises(ValidationError):
        ClassificationOutput.model_validate(
            {"labels": [{"grounding": "explicit", "evidence": "x", "kind": "doctrinal"}]})


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
