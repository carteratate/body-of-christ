import pytest
from enrichment.prompts.base import compose_generation_system
from enrichment.prompts.generation import generation_system
from enrichment.prompts.classification import classification_system, COLLECTION_NOTES
from enrichment.prompts.annotation import ANNOTATION_SYSTEM

ALL = ["bible", "catechism", "summa", "encyclicals", "church-fathers",
       "medieval", "councils", "canon-law", "apostolic-exhortations", "papal-documents"]


# --- Pass 1: generation scaffolding ---

def test_compose_injects_guidance():
    s = compose_generation_system("COLLECTION GUIDANCE MARKER")
    assert "COLLECTION GUIDANCE MARKER" in s
    assert "2" in s and "12" in s  # facet count bounds mentioned


def test_compose_no_longer_asks_for_annotation():
    s = compose_generation_system("marker")
    assert "SUMMARY:" not in s  # the old annotation-format block is gone
    assert "Hard cap ~400-600 tokens" not in s


def test_compose_output_contract_defers_labels_and_annotation():
    s = compose_generation_system("marker")
    assert "Do not assign labels or write an annotation" in s


def test_compose_question_is_single_clause():
    s = compose_generation_system("marker").lower()
    assert "single question" in s or "one clause" in s


def test_compose_describes_three_part_facet_in_order():
    s = compose_generation_system("marker")
    assert s.index("TEXT —") < s.index("TAKEAWAY —") < s.index("QUESTION —")


def test_compose_takeaway_word_and_sentence_bounds():
    s = compose_generation_system("marker")
    assert "1-2 sentences, 30-70 words" in s


def test_compose_takeaway_forbids_banned_openers():
    s = compose_generation_system("marker")
    assert '"Thus," "Therefore," or "In this way."' in s


def test_compose_output_contract_lists_all_three_fields():
    s = compose_generation_system("marker")
    assert "`text`, `takeaway`, and `question`" in s


@pytest.mark.parametrize("collection", ALL)
def test_every_collection_has_a_generation_prompt(collection):
    s = generation_system(collection)
    assert isinstance(s, str) and len(s) > 200
    assert "ANNOTATION" not in s


def test_unknown_collection_raises():
    with pytest.raises(KeyError):
        generation_system("nonexistent")


@pytest.mark.parametrize("collection", ALL)
def test_guidance_no_longer_uses_kind_quota_language(collection):
    s = generation_system(collection)
    assert "Favor `" not in s
    assert "angles." not in s


@pytest.mark.parametrize("collection", ALL)
def test_guidance_mentions_question_style(collection):
    s = generation_system(collection)
    assert "Questions:" in s


# --- Pass 2: classification ---

def test_classification_prompt_lists_full_taxonomy():
    s = classification_system("bible")
    for term in ["explicit", "settled", "inferential",
                 "doctrinal", "scriptural", "typological", "philosophical",
                 "moral", "historical", "devotional"]:
        assert term in s


def test_classification_splices_collection_note():
    s = classification_system("canon-law")
    assert COLLECTION_NOTES["canon-law"] in s


@pytest.mark.parametrize("collection", ALL)
def test_every_collection_has_a_classification_note(collection):
    assert collection in COLLECTION_NOTES
    assert len(COLLECTION_NOTES[collection]) > 20


def test_classification_unknown_collection_raises():
    with pytest.raises(KeyError):
        classification_system("nonexistent")


def test_classification_evidence_must_be_single_contiguous_span():
    s = classification_system("bible")
    assert "single contiguous span" in s
    assert "no stitching" in s


def test_classification_evidence_style_line_for_settled_and_inferential():
    s = classification_system("bible")
    assert "evidence` for settled and inferential must be ONE clause" in s


def test_classification_mentions_kind_secondary():
    s = classification_system("bible")
    assert "kind_secondary" in s


def test_classification_forbids_distributing_for_variety():
    s = classification_system("bible")
    assert "Do not distribute labels to achieve variety" in s


# --- Pass 3: annotation assembly ---

def test_annotation_system_mentions_grounding_and_kind():
    assert "grounding" in ANNOTATION_SYSTEM
    assert "kind" in ANNOTATION_SYSTEM.lower()


def test_annotation_system_forbids_relabeling():
    assert "Never re-judge, change, or omit a label" in ANNOTATION_SYSTEM


def test_annotation_system_requires_different_wording():
    assert "DIFFERENT wording" in ANNOTATION_SYSTEM
