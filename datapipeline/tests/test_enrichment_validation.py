import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

import pytest
from enrichment.schema import GenFacet, IdentifiedFacet, Label
from enrichment.validation import (
    ValidationFailedError, normalize_for_containment,
    validate_classification, reorder_labels_by_facet_id, validate_annotation,
    split_sentences, check_takeaway, validate_generation, validate_evidence_style,
)

CONTENT = "In the beginning God created the heavens and the earth."


def _facet(id="f1", text="f", question="q", takeaway="tk"):
    return IdentifiedFacet(id=id, text=text, takeaway=takeaway, question=question)


def _label(facet_id="f1", grounding="explicit", evidence="God created the heavens and the earth",
           kind="doctrinal", kind_secondary=None):
    return Label(facet_id=facet_id, grounding=grounding, evidence=evidence, kind=kind,
                 kind_secondary=kind_secondary)


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
    facets = [_facet(id="f1"), _facet(id="f2")]
    labels = [_label(facet_id="f1")]
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


# --- validate_classification: facet_id bijection (identity, never position) ---

def test_classification_accepts_reordered_labels_matched_by_facet_id():
    facets = [_facet(id="f1"), _facet(id="f2")]
    # labels come back in the opposite order — still valid, joined by facet_id
    labels = [_label(facet_id="f2", kind="moral"), _label(facet_id="f1", kind="doctrinal")]
    validate_classification(facets, labels, CONTENT)  # should not raise


def test_classification_fails_on_missing_facet_id():
    facets = [_facet(id="f1"), _facet(id="f2")]
    labels = [_label(facet_id="f1"), _label(facet_id="f1")]  # f2 never classified
    with pytest.raises(ValidationFailedError) as exc_info:
        validate_classification(facets, labels, CONTENT)
    assert any("missing classification for facet_id" in e for e in exc_info.value.errors)


def test_classification_fails_on_duplicate_facet_id():
    facets = [_facet(id="f1"), _facet(id="f2")]
    labels = [_label(facet_id="f1"), _label(facet_id="f1")]
    with pytest.raises(ValidationFailedError) as exc_info:
        validate_classification(facets, labels, CONTENT)
    assert any("duplicate facet_id" in e for e in exc_info.value.errors)


def test_classification_fails_on_unknown_facet_id():
    facets = [_facet(id="f1"), _facet(id="f2")]
    labels = [_label(facet_id="f1"), _label(facet_id="f99")]
    with pytest.raises(ValidationFailedError) as exc_info:
        validate_classification(facets, labels, CONTENT)
    assert any("unknown facet_id" in e for e in exc_info.value.errors)


def test_classification_never_silently_repairs_reordered_ids_missing_evidence():
    # Even a facet_id mismatch that "looks fixable" (e.g. off-by-one) must be
    # rejected outright rather than guessed at.
    facets = [_facet(id="f1"), _facet(id="f2"), _facet(id="f3")]
    labels = [_label(facet_id="f1"), _label(facet_id="f2")]  # missing f3, only 2 of 3
    with pytest.raises(ValidationFailedError):
        validate_classification(facets, labels, CONTENT)


# --- reorder_labels_by_facet_id ---

def test_reorder_labels_by_facet_id_realigns_to_facet_order():
    facets = [_facet(id="f1"), _facet(id="f2"), _facet(id="f3")]
    labels = [_label(facet_id="f3", kind="historical"),
             _label(facet_id="f1", kind="doctrinal"),
             _label(facet_id="f2", kind="moral")]
    ordered = reorder_labels_by_facet_id(facets, labels)
    assert [lab.facet_id for lab in ordered] == ["f1", "f2", "f3"]
    assert [lab.kind for lab in ordered] == ["doctrinal", "moral", "historical"]


def test_reorder_labels_by_facet_id_is_identity_when_already_in_order():
    facets = [_facet(id="f1"), _facet(id="f2")]
    labels = [_label(facet_id="f1", kind="doctrinal"), _label(facet_id="f2", kind="moral")]
    ordered = reorder_labels_by_facet_id(facets, labels)
    assert [lab.kind for lab in ordered] == ["doctrinal", "moral"]


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


def test_annotation_no_warning_for_short_complete_annotation_below_target():
    # A short, complete annotation must never be warned about merely for being
    # shorter than the facet-aware target (target for 1 facet is 45+45=90).
    facets = [_fwl()]
    annotation = "SUMMARY: short.\n\n[DOCTRINAL | explicit]: tiny."
    warnings = validate_annotation(facets, annotation)
    assert not any("token" in w for w in warnings)


def test_annotation_warns_when_materially_above_facet_aware_target():
    # 1 facet -> target 90, soft threshold max(90+75, ceil(90*1.25))=165.
    # 500-token body is far past that, so this must warn.
    facets = [_fwl()]
    body = " ".join(["word"] * 500)
    annotation = f"SUMMARY: {body}\n\n[DOCTRINAL | explicit]: text."
    warnings = validate_annotation(facets, annotation)
    assert any("token" in w for w in warnings)
    assert any("target of ~90 tokens" in w for w in warnings)


def test_annotation_hard_fails_when_exceeding_800_tokens():
    facets = [_fwl()]
    body = " ".join(["word"] * 850)
    annotation = f"SUMMARY: {body}\n\n[DOCTRINAL | explicit]: text."
    with pytest.raises(ValidationFailedError) as exc_info:
        validate_annotation(facets, annotation)
    assert any("800" in e for e in exc_info.value.errors)


def _build_annotation(n_facets: int, summary_tokens: int, segment_tokens: int) -> str:
    """Builds a structurally valid annotation (1 SUMMARY line + n_facets
    segments, all doctrinal/explicit) with a precisely controllable token
    count. Empirically (cl100k_base): "word" tokenizes to exactly 1 token,
    "SUMMARY: " to 4, and each "[DOCTRINAL | explicit]: " header to 8, with a
    constant +1 token of overhead from the blank line after SUMMARY — so the
    total is exactly 5 + summary_tokens + n_facets * (8 + segment_tokens)."""
    summary_body = " ".join(["word"] * summary_tokens)
    segments = "\n".join(
        "[DOCTRINAL | explicit]: " + " ".join(["word"] * segment_tokens)
        for _ in range(n_facets)
    )
    return f"SUMMARY: {summary_body}\n\n{segments}"


def _segment_tokens_for_total(n_facets: int, summary_tokens: int, desired_total: int) -> int:
    """Inverts _build_annotation's exact token formula to hit `desired_total`."""
    return max((desired_total - 5 - summary_tokens) // n_facets - 8, 1)


def _expected_threshold(target: int) -> int:
    import math
    return max(target + 75, math.ceil(target * 1.25))


@pytest.mark.parametrize("n", [2, 5, 8, 12])
def test_annotation_target_tokens_formula_boundary(n):
    from enrichment.validation import annotation_target_tokens
    assert annotation_target_tokens(n) == 45 + 45 * n


@pytest.mark.parametrize("n", [2, 5, 8, 12])
def test_annotation_no_warning_at_facet_aware_target(n):
    facets = [_fwl() for _ in range(n)]
    target = 45 + 45 * n
    # Land comfortably at/under the target (well inside the soft threshold).
    summary_tokens = 20
    seg_tokens = _segment_tokens_for_total(n, summary_tokens, desired_total=target - 30)
    annotation = _build_annotation(n, summary_tokens, seg_tokens)
    warnings = validate_annotation(facets, annotation)
    assert not any("token" in w for w in warnings)


@pytest.mark.parametrize("n", [2, 5, 8, 12])
def test_annotation_warns_when_materially_above_target_for_facet_count(n):
    facets = [_fwl() for _ in range(n)]
    target = 45 + 45 * n
    threshold = _expected_threshold(target)
    # Comfortably past the soft threshold, capped well under the 800 hard cap.
    summary_tokens = 20
    desired_total = min(threshold + 50, 795)
    seg_tokens = _segment_tokens_for_total(n, summary_tokens, desired_total)
    annotation = _build_annotation(n, summary_tokens, seg_tokens)
    warnings = validate_annotation(facets, annotation)
    assert any("token" in w for w in warnings)


@pytest.mark.parametrize("n", [2, 5, 8, 12])
def test_annotation_soft_threshold_formula_boundary(n):
    from enrichment.validation import annotation_target_tokens, _annotation_soft_threshold
    target = annotation_target_tokens(n)
    assert _annotation_soft_threshold(target) == _expected_threshold(target)


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
    # The prompt asks for 2-4 sentences; the hard cap is 4.
    takeaway = ("First sentence here now. Second sentence follows next. "
               "Third sentence continues the thought further still. "
               "Fourth sentence adds one more point to consider. "
               "Fifth sentence breaks the four sentence limit entirely today.")
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert any(f.startswith("sentence_count") for f in failures)


def test_check_takeaway_allows_up_to_four_sentences():
    takeaway = ("First sentence here now. Second sentence follows next. "
               "Third sentence continues the thought further still. "
               "Fourth sentence completes the takeaway about David's kingship today.")
    failures = check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE)
    assert not any(f.startswith("sentence_count") for f in failures)


def test_check_takeaway_allows_abstract_takeaway_with_no_shared_vocabulary():
    # No proper noun and no >=6-char word shared with PASSAGE. The removed
    # `concreteness` check hard-failed exactly this shape, which the prompt no
    # longer asks to avoid — abstract synthesis over poetic or wisdom
    # literature routinely looks like this and must not cost a retry.
    takeaway = ("This general statement discusses something without naming any "
               "specific incident, individual, document, or location, relying "
               "only on common short terms rather than naming any concrete "
               "detail whatsoever throughout the whole passage.")
    assert check_takeaway(takeaway, GOOD_WORKING_TEXT, PASSAGE) == []


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


# Five sentences — trips `sentence_count`, the only remaining takeaway check
# that a synthetic takeaway can violate without also copying the working text.
_FIVE_SENTENCES = ("One sentence here. Two sentences here. Three sentences here. "
                   "Four sentences here. Five sentences here.")


def test_validate_generation_raises_with_facet_index_prefix():
    bad = _gen_facet(takeaway=_FIVE_SENTENCES)
    with pytest.raises(ValidationFailedError) as exc_info:
        validate_generation([_gen_facet(), bad], PASSAGE)
    assert any(m.startswith("facet[1]") for m in exc_info.value.errors)


def test_validate_generation_aggregates_across_multiple_facets():
    bad1 = _gen_facet(takeaway=_FIVE_SENTENCES)
    bad2 = _gen_facet(takeaway=GOOD_WORKING_TEXT)  # anti_copy: verbatim working text
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


def test_evidence_style_warns_on_multiple_citations_for_settled():
    labels = [_label(grounding="settled",
                     evidence="see John 19:36 and also CCC 613 for this reading")]
    warnings = validate_evidence_style(labels)
    assert any(w.startswith("label[0] evidence_citations") for w in warnings)


def test_evidence_style_does_not_warn_on_multiple_citations_for_inferential():
    # Item 6: inferential evidence is never penalized for citing external
    # references — citing an outside connection is expected at this tier.
    labels = [_label(grounding="inferential",
                     evidence="see John 19:36 and also CCC 613 for this reading")]
    warnings = validate_evidence_style(labels)
    assert not any(w.startswith("label[0] evidence_citations") for w in warnings)


def test_evidence_style_warns_on_settled_tradition_signal():
    labels = [_label(grounding="settled",
                     evidence="this follows from the Church's tradition")]
    warnings = validate_evidence_style(labels)
    assert any(w.startswith("label[0] settled_consistency") for w in warnings)


def test_evidence_style_no_tradition_signal_warning_for_inferential():
    # The consistency check only applies to settled — an inferential label
    # naming tradition/an external connection is expected, not a smell.
    labels = [_label(grounding="inferential",
                     evidence="this follows from the Church's tradition")]
    warnings = validate_evidence_style(labels)
    assert not any(w.startswith("label[0] settled_consistency") for w in warnings)


def test_evidence_style_allows_single_citation():
    labels = [_label(grounding="settled", evidence="NT citation: John 19:36")]
    assert validate_evidence_style(labels) == []
