"""Document/card building must work for enriched AND unenriched candidates.

Enrichment is rolled out per collection, so both branches are live simultaneously.
"""
from __future__ import annotations

from app.rag.steps.rerank_docs import cohere_document, llm_card
from app.rag.steps.types import ChunkCandidate

_ANNOTATION = (
    "SUMMARY: The Red Sea crossing as deliverance through affliction.\n"
    "[scriptural | explicit]: Israel passes through the sea on dry ground.\n"
    "[typological/doctrinal | inferential]: The crossing prefigures baptismal passage "
    "from slavery to freedom."
)


def _candidate(annotation: str | None = None,
               unit_label: str | None = None) -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id="00000000-0000-0000-0000-000000000001",
        content="And Moses stretched out his hand over the sea.",
        reference="Exodus 14:21",
        collection="bible",
        document_id="d1",
        document_title="Exodus",
        author=None,
        rrf_score=0.5,
        annotation=annotation,
        unit_label=unit_label,
    )


# --- cohere_document ---

def test_cohere_document_unenriched_matches_historical_format():
    """The pre-refactor format was f"[{ref or collection}] {content}" — an unenriched
    candidate must reproduce it byte-for-byte so the baseline pipeline is unchanged."""
    c = _candidate()
    assert cohere_document(c) == f"[{c.reference}] {c.content}"


def test_cohere_document_falls_back_to_collection_when_reference_missing():
    c = _candidate()
    c.reference = None
    assert cohere_document(c) == f"[bible] {c.content}"


def test_cohere_document_includes_annotation_when_enriched():
    doc = cohere_document(_candidate(_ANNOTATION))
    assert "SUMMARY:" in doc
    assert "And Moses stretched out his hand" in doc


def test_cohere_document_preserves_kind_and_grounding_labels():
    """Guards against a future refactor reaching for `annotation_prose()`, which
    strips these labels — they are the signal a cross-encoder cannot infer from the
    narrative's surface wording."""
    doc = cohere_document(_candidate(_ANNOTATION))
    assert "[scriptural | explicit]" in doc
    assert "[typological/doctrinal | inferential]" in doc


def test_cohere_document_puts_annotation_before_content():
    """max_tokens_per_doc truncates from the end, so content must be last."""
    doc = cohere_document(_candidate(_ANNOTATION))
    assert doc.index("SUMMARY:") < doc.index("And Moses stretched")


# --- llm_card ---

def test_llm_card_includes_chunk_id_and_collection():
    card = llm_card(_candidate())
    assert "00000000-0000-0000-0000-000000000001" in card
    assert "(bible)" in card


def test_llm_card_includes_annotation_when_enriched():
    assert "SUMMARY:" in llm_card(_candidate(_ANNOTATION))


def test_llm_card_omits_annotation_line_when_unenriched():
    card = llm_card(_candidate())
    assert "SUMMARY:" not in card
    assert card.count("\n") == 1  # header + content only


def test_llm_card_truncates_content_but_not_annotation():
    long = _candidate(_ANNOTATION)
    long.content = "x" * 5000
    card = llm_card(long, max_content_chars=100)
    assert "SUMMARY:" in card
    assert "[typological/doctrinal | inferential]" in card
    assert "x" * 200 not in card
    assert card.endswith("...")


# ---------------------------------------------------------------------------
# unit_label — the passage's role in its document.
#
# 10,517 Summa chunks (39.3% of that collection) are objections Aquinas states in
# order to REFUTE. Without the label a reranker sees only "It would seem that..."
# and can rank the negation of Catholic teaching as though it were his own.
# ---------------------------------------------------------------------------

def test_cohere_document_omits_unit_label_when_absent():
    """Collections with no dialectical structure must be byte-identical to before."""
    c = _candidate()
    assert cohere_document(c) == f"[{c.reference}] {c.content}"


def test_cohere_document_includes_unit_label_when_present():
    c = _candidate(unit_label="Objection 1")
    assert cohere_document(c) == f"[{c.reference}] [Objection 1] {c.content}"


def test_cohere_document_places_unit_label_before_annotation():
    """Cohere truncates from the END at max_tokens_per_doc, so the label has to sit
    ahead of the annotation and content or a long passage can lose it."""
    c = _candidate(annotation=_ANNOTATION, unit_label="Objection 1")
    doc = cohere_document(c)
    assert doc.index("Objection 1") < doc.index("SUMMARY:") < doc.index(c.content)


def test_llm_card_omits_unit_label_when_absent():
    c = _candidate()
    assert "—" not in llm_card(c).splitlines()[0]


def test_llm_card_puts_unit_label_in_the_header():
    c = _candidate(unit_label="Reply to Objection 2")
    assert llm_card(c).splitlines()[0].endswith("— Reply to Objection 2")


def test_llm_card_never_truncates_the_unit_label():
    """Content is truncated to fit the listwise prompt; the label must not be, or a
    long objection's card reads as the author's own teaching."""
    c = _candidate(unit_label="Objection 1")
    c.content = "x" * 5000
    card = llm_card(c, max_content_chars=50)
    assert "Objection 1" in card
    assert len(card) < 400


def test_llm_card_omits_a_redundant_role():
    """The listwise card is the PRODUCTION path (hyde_cohere_luna) and was the one
    suppression branch with no test — a mutation reverting it passed the whole suite."""
    c = _candidate(unit_label="Can. 33")
    c.reference = "Code of Canon Law, Can. 33"
    c.collection = "canon-law"
    assert llm_card(c).splitlines()[0] == (
        f"[{c.chunk_id}] (canon-law) Code of Canon Law, Can. 33"
    )
