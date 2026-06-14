import uuid

from identity import DOCUMENT_NS, slugify, document_id, anchor


def test_slugify_basic():
    assert slugify("First Epistle to the Corinthians") == "first-epistle-to-the-corinthians"


def test_slugify_strips_punct_and_case():
    assert slugify("  Q. 68, A. 3!  ") == "q-68-a-3"
    assert slugify("John") == "john"


def test_document_id_is_uuid_string():
    did = document_id("bible", "WEB-C", "John")
    assert isinstance(did, str)
    uuid.UUID(did)  # parses without raising


def test_document_id_deterministic():
    assert document_id("bible", "WEB-C", "John") == document_id("bible", "WEB-C", "John")


def test_document_id_distinguishes_inputs():
    assert document_id("bible", "WEB-C", "John") != document_id("bible", "WEB-C", "Mark")
    assert document_id("bible", "WEB-C", "John") != document_id("bible", "DRA", "John")


def test_document_id_uses_fixed_namespace():
    # Guards against an accidental namespace change that would re-key every document.
    assert str(DOCUMENT_NS) == "8b4a9d2e-1c6f-4e7a-bf3d-2a5c9e0f17b6"


def test_anchor_numbers_preserved():
    assert anchor("john", 3, 16) == "john/3/16"


def test_anchor_slugifies_text_segments():
    assert anchor("First Epistle", "Chapter 49") == "first-epistle/chapter-49"
    assert anchor("i-ii", "q68", "a3", "i-answer") == "i-ii/q68/a3/i-answer"


def test_passage_id_deterministic_and_unique():
    from identity import passage_id
    did = document_id("bible", "WEB-C", "John")
    pid = passage_id(did, "john/3/16")
    assert pid == passage_id(did, "john/3/16")              # both writers agree
    assert pid != passage_id(did, "john/3/17")              # unique per anchor
    uuid.UUID(pid)
