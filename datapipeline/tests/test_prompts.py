import pytest
from enrichment.prompts.classification import CLASSIFICATION_SYSTEM
from enrichment.prompts.base import compose_generation_system
from enrichment.prompts.generation import generation_system

ALL = ["bible", "catechism", "summa", "encyclicals", "church-fathers",
       "medieval", "councils", "canon-law", "apostolic-exhortations", "papal-documents"]


def test_classification_prompt_lists_full_taxonomy():
    for term in ["explicit", "traditional", "inferential",
                 "doctrinal", "scriptural", "typological", "philosophical",
                 "moral", "historical", "devotional"]:
        assert term in CLASSIFICATION_SYSTEM


def test_compose_injects_guidance():
    s = compose_generation_system("COLLECTION GUIDANCE MARKER")
    assert "COLLECTION GUIDANCE MARKER" in s
    assert "2" in s and "12" in s  # facet count bounds mentioned


@pytest.mark.parametrize("collection", ALL)
def test_every_collection_has_a_generation_prompt(collection):
    s = generation_system(collection)
    assert isinstance(s, str) and len(s) > 200


def test_unknown_collection_raises():
    with pytest.raises(KeyError):
        generation_system("nonexistent")
