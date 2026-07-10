import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

import pytest
from enrichment.schema import GenFacet, Label
from enrichment.validation import (
    ValidationFailedError, normalize_for_containment,
    validate_classification, validate_annotation, split_sentences,
    check_takeaway, validate_generation, validate_evidence_style,
)

CONTENT = "In the beginning God created the heavens and the earth."


def _facet(text="f", question="q", takeaway="tk"):
    return GenFacet(text=text, takeaway=takeaway, question=question)


def _label(grounding="explicit", evidence="God created the heavens and the earth",
           kind="doctrinal", kind_secondary=None):
    return Label(grounding=grounding, evidence=evidence, kind=kind, kind_secondary=kind_secondary)


# --- split_sentences: conservative splitter, must not be fooled by abbreviations
# (St., cf., v., ch.) or verse references (1 Cor. 11:23) that are full of periods ---

def test_split_two_plain_sentences():
    assert split_sentences("This is one sentence. This is another.") == \
        ["This is one sentence.", "This is another."]


def test_split_single_sentence_no_period_needed():
    assert split_sentences("Just one sentence with no trailing period") == \
        ["Just one sentence with no trailing period"]


def test_split_does_not_break_on_st_abbreviation():
    assert split_sentences("St. Paul writes about love. He emphasizes charity.") == \
        ["St. Paul writes about love.", "He emphasizes charity."]


def test_split_does_not_break_on_cf_abbreviation():
    assert split_sentences("cf. Genesis 1:1 for the creation account. It is foundational.") == \
        ["cf. Genesis 1:1 for the creation account.", "It is foundational."]


def test_split_does_not_break_on_verse_reference_abbreviation():
    # "Cor." followed by a digit never triggers a split attempt at all (only
    # capital-letter or quote continuations do), but this locks in that behavior.
    assert split_sentences("Paul explains this in 1 Cor. 11:23 clearly.") == \
        ["Paul explains this in 1 Cor. 11:23 clearly."]


def test_split_does_not_break_on_chapter_and_verse_abbreviations():
    assert split_sentences("The prophecy in Isa. 53:5 is fulfilled here. Christ bore our griefs.") == \
        ["The prophecy in Isa. 53:5 is fulfilled here.", "Christ bore our griefs."]


def test_split_does_not_break_on_title_abbreviations():
    assert split_sentences("Fr. Brown and Dr. Smith agree. Both cite the same source.") == \
        ["Fr. Brown and Dr. Smith agree.", "Both cite the same source."]


def test_split_does_not_break_on_saint_name_mid_sentence():
    assert split_sentences(
        "St. Thomas Aquinas argues this in the Summa. He also defends it elsewhere."
    ) == ["St. Thomas Aquinas argues this in the Summa.", "He also defends it elsewhere."]


def test_split_handles_question_and_exclamation_marks():
    assert split_sentences("Why does this matter? It changes everything!") == \
        ["Why does this matter?", "It changes everything!"]


def test_split_handles_sentence_starting_with_open_quote():
    assert split_sentences('He said "come and see." Then he left.') == \
        ['He said "come and see."', "Then he left."]


def test_split_three_sentences():
    assert split_sentences("First. Second. Third.") == ["First.", "Second.", "Third."]


# --- normalize_for_containment ---

def test_normalize_collapses_whitespace_and_case_and_punctuation():
    a = normalize_for_containment("God created  the Heavens, and the earth.")
    b = normalize_for_containment("god created the heavens and the earth")
    assert a == b


def test_normalize_treats_curly_and_straight_apostrophes_as_equivalent():
    # e.g. WEB Bible text uses a curly apostrophe ("LORD’s"); model output
    # commonly uses a straight one ("LORD's") — both must normalize the same.
    curly = normalize_for_containment("the LORD’s word by Samuel")
    straight = normalize_for_containment("the LORD's word by Samuel")
    assert curly == straight


def test_normalize_treats_curly_and_straight_double_quotes_as_equivalent():
    curly = normalize_for_containment("he said, “behold”")
    straight = normalize_for_containment('he said, "behold"')
    assert curly == straight


def test_classification_explicit_evidence_matches_despite_curly_apostrophe_in_content():
    content_with_curly_quote = "They anointed David king, according to the LORD’s word by Samuel."
    facets = [_facet()]
    labels = [_label(grounding="explicit",
                     evidence="according to the LORD's word by Samuel")]
    validate_classification(facets, labels, content_with_curly_quote)  # should not raise


# --- validate_classification ---

def test_classification_passes_with_matching_counts_and_explicit_quote():
    facets = [_facet()]
    labels = [_label()]
    validate_classification(facets, labels, CONTENT)  # should not raise


def test_classification_fails_on_facet_label_count_mismatch():
    facets = [_facet(), _facet()]
    labels = [_label()]
    with pytest.raises(ValidationFailedError):
        validate_classification(facets, labels, CONTENT)


def test_classification_fails_on_empty_evidence():
    facets = [_facet()]
    labels = [_label(evidence="   ")]
    with pytest.raises(ValidationFailedError):
        validate_classification(facets, labels, CONTENT)


def test_classification_fails_when_explicit_evidence_not_in_content():
    facets = [_facet()]
    labels = [_label(grounding="explicit", evidence="this is not in the passage at all")]
    with pytest.raises(ValidationFailedError):
        validate_classification(facets, labels, CONTENT)


def test_classification_explicit_quote_check_tolerates_punctuation_and_case_differences():
    facets = [_facet()]
    labels = [_label(grounding="explicit", evidence="GOD CREATED THE HEAVENS AND THE EARTH")]
    validate_classification(facets, labels, CONTENT)  # should not raise


def test_classification_settled_grounding_does_not_require_verbatim_quote():
    facets = [_facet()]
    labels = [_label(grounding="settled", evidence="tradition-pattern: not a literal quote")]
    validate_classification(facets, labels, CONTENT)  # should not raise


# --- validate_annotation ---

def _fwl(kind="doctrinal", grounding="explicit", kind_secondary=None):
    return {"text": "t", "question": "q", "grounding": grounding,
            "evidence": "e", "kind": kind, "kind_secondary": kind_secondary}


def test_annotation_passes_with_matching_segments():
    facets = [_fwl()]
    annotation = "SUMMARY: a brief summary.\n\n[DOCTRINAL | explicit]: some text here."
    warnings = validate_annotation(facets, annotation)
    assert isinstance(warnings, list)


def test_annotation_fails_without_summary_line():
    facets = [_fwl()]
    annotation = "[DOCTRINAL | explicit]: some text here."
    with pytest.raises(ValidationFailedError):
        validate_annotation(facets, annotation)


def test_annotation_fails_on_segment_count_mismatch():
    facets = [_fwl(), _fwl()]
    annotation = "SUMMARY: a brief summary.\n\n[DOCTRINAL | explicit]: some text here."
    with pytest.raises(ValidationFailedError):
        validate_annotation(facets, annotation)


def test_annotation_fails_on_label_mismatch():
    facets = [_fwl(kind="doctrinal", grounding="explicit")]
    annotation = "SUMMARY: a brief summary.\n\n[MORAL | explicit]: some text here."
    with pytest.raises(ValidationFailedError):
        validate_annotation(facets, annotation)


def test_annotation_handles_secondary_kind_in_header():
    facets = [_fwl(kind="doctrinal", grounding="settled", kind_secondary="moral")]
    annotation = "SUMMARY: a brief summary.\n\n[DOCTRINAL/MORAL | settled]: some text here."
    warnings = validate_annotation(facets, annotation)
    assert isinstance(warnings, list)


def test_annotation_fails_when_secondary_kind_missing_from_header():
    facets = [_fwl(kind="doctrinal", grounding="settled", kind_secondary="moral")]
    annotation = "SUMMARY: a brief summary.\n\n[DOCTRINAL | settled]: some text here."
    with pytest.raises(ValidationFailedError):
        validate_annotation(facets, annotation)


def test_annotation_soft_warns_when_outside_token_target():
    facets = [_fwl()]
    annotation = "SUMMARY: short.\n\n[DOCTRINAL | explicit]: tiny."
    warnings = validate_annotation(facets, annotation)
    assert any("token" in w for w in warnings)


def test_annotation_no_warning_when_within_token_target():
    facets = [_fwl()]
    body = " ".join(["word"] * 500)
    annotation = f"SUMMARY: {body}\n\n[DOCTRINAL | explicit]: text."
    warnings = validate_annotation(facets, annotation)
    assert not any("token" in w for w in warnings)


# --- check_takeaway / validate_generation (Pass 1 hard validation) ---

PASSAGE = ("David made a covenant with the elders of Israel at Hebron "
          "before the LORD.")

GOOD_TAKEAWAY = (
    "David's kingship over Israel was formally established through a solemn "
    "covenant sworn before the LORD at Hebron, binding king and people under "
    "divine witness rather than mere conquest or dynastic claim."
)
GOOD_WORKING_TEXT = (
    "The elders came to David at Hebron and made a covenant with him there "
    "before the LORD, ratifying what his years of service had already earned him."
)


def test_check_takeaway_passes_a_well_formed_takeaway():
    assert check_takeaway(GOOD_TAKEAWAY, GOOD_WORKING_TEXT, PASSAGE) == []


def test_check_takeaway_flags_too_many_sentences():
    takeaway = ("First sentence here now. Second sentence follows next. "
               "Third sentence breaks the two sentence limit entirely today.")
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert any(f.startswith("sentence_count") for f in failures)


def test_check_takeaway_flags_too_few_words():
    takeaway = " ".join(["word"] * 10) + "."
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert any(f.startswith("word_count") for f in failures)


def test_check_takeaway_flags_too_many_words():
    takeaway = " ".join(["word"] * 80) + "."
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert any(f.startswith("word_count") for f in failures)


@pytest.mark.parametrize("opener", ["Thus", "Therefore", "Hence", "In this way"])
def test_check_takeaway_flags_banned_openers(opener):
    takeaway = (f"{opener}, the kingship of David over all Israel was firmly "
               f"and permanently established through the solemn covenant at "
               f"Hebron before the LORD and the assembled elders of the tribes.")
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert any(f.startswith("banned_opener") for f in failures)


def test_check_takeaway_banned_opener_ignores_leading_quote():
    takeaway = ('"Thus the kingship of David over all Israel was firmly and '
               'permanently established through the solemn covenant at Hebron '
               'before the LORD and the assembled elders of the tribes."')
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert any(f.startswith("banned_opener") for f in failures)


def test_check_takeaway_allows_thus_mid_sentence():
    # "Thus" is only banned as a sentence opener, not mid-sentence.
    takeaway = ("David's kingship over Israel was established thus: a solemn "
               "covenant sworn before the LORD at Hebron bound king and people "
               "together under divine witness rather than mere conquest.")
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert not any(f.startswith("banned_opener") for f in failures)


def test_check_takeaway_flags_lack_of_concreteness():
    takeaway = ("This general statement discusses something without naming any "
               "specific incident, individual, document, or location, relying "
               "only on common short terms rather than naming any concrete "
               "detail whatsoever throughout the whole passage.")
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert any(f.startswith("concreteness") for f in failures)


def test_check_takeaway_concreteness_passes_with_shared_long_word_even_without_proper_noun():
    takeaway = ("A solemn covenant established royal authority through mutual "
               "obligation and divine witness rather than through conquest or "
               "inherited succession, binding ruler and community together.")
    # "covenant" (>=6 chars) appears verbatim in PASSAGE, satisfying the
    # content-word-overlap branch even with no capitalized non-initial token.
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert not any(f.startswith("concreteness") for f in failures)


def test_check_takeaway_flags_verbatim_copy_of_working_text():
    working_text = (
        "David's kingship over Israel was formally established through a solemn "
        "covenant sworn before the LORD at Hebron, binding king and people under "
        "divine witness rather than mere conquest or dynastic claim. This is "
        "elaborated further with additional theological reflection on covenant kingship."
    )
    failures = check_takeaway(GOOD_TAKEAWAY, working_text, PASSAGE)
    assert any(f.startswith("anti_copy") for f in failures)


def test_check_takeaway_curly_quotes_dont_cause_false_anti_copy_negative():
    # The anti-copy check must reuse the same curly-quote-aware normalization
    # as the Pass 2 quote check — not a second, subtly different normalizer.
    working_text = "David’s kingship over Israel was formally established " + GOOD_TAKEAWAY[len("David's kingship over Israel was formally established"):]
    failures = check_takeaway(GOOD_TAKEAWAY, working_text, PASSAGE)
    assert any(f.startswith("anti_copy") for f in failures)


def _gen_facet(text=GOOD_WORKING_TEXT, takeaway=GOOD_TAKEAWAY, question="q"):
    return GenFacet(text=text, takeaway=takeaway, question=question)


def test_validate_generation_passes_well_formed_facets():
    validate_generation([_gen_facet()], PASSAGE)  # should not raise


def test_validate_generation_raises_with_facet_index_prefix():
    bad = _gen_facet(takeaway=" ".join(["word"] * 5) + ".")
    with pytest.raises(ValidationFailedError) as exc_info:
        validate_generation([_gen_facet(), bad], PASSAGE)
    assert any(m.startswith("facet[1]") for m in exc_info.value.errors)


def test_validate_generation_aggregates_across_multiple_facets():
    bad1 = _gen_facet(takeaway=" ".join(["word"] * 5) + ".")
    bad2 = _gen_facet(takeaway="Thus " + " ".join(["word"] * 35) + ".")
    with pytest.raises(ValidationFailedError) as exc_info:
        validate_generation([bad1, bad2], PASSAGE)
    assert any(m.startswith("facet[0]") for m in exc_info.value.errors)
    assert any(m.startswith("facet[1]") for m in exc_info.value.errors)


# --- validate_evidence_style (Pass 2 soft warnings; settled/inferential only) ---

def test_evidence_style_ignores_explicit_labels():
    labels = [_label(grounding="explicit",
                     evidence="a very long evidence quote " * 5 + "with; a semicolon")]
    assert validate_evidence_style(labels) == []


def test_evidence_style_warns_on_long_evidence():
    labels = [_label(grounding="settled", evidence=" ".join(["word"] * 30))]
    warnings = validate_evidence_style(labels)
    assert any(w.startswith("label[0] evidence_length") for w in warnings)


def test_evidence_style_ok_within_word_cap():
    labels = [_label(grounding="settled", evidence=" ".join(["word"] * 10))]
    assert validate_evidence_style(labels) == []


def test_evidence_style_warns_on_semicolon():
    labels = [_label(grounding="inferential", evidence="one warrant; another warrant too")]
    warnings = validate_evidence_style(labels)
    assert any(w.startswith("label[0] evidence_semicolon") for w in warnings)


def test_evidence_style_warns_on_multiple_citations():
    labels = [_label(grounding="settled",
                     evidence="see John 19:36 and also CCC 613 for this reading")]
    warnings = validate_evidence_style(labels)
    assert any(w.startswith("label[0] evidence_citations") for w in warnings)


def test_evidence_style_allows_single_citation():
    labels = [_label(grounding="settled", evidence="NT citation: John 19:36")]
    assert validate_evidence_style(labels) == []
