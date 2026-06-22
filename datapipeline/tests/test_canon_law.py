import sys, os

# Set required env vars before importing ingest.canon_law, which imports config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from ingest.canon_law import (
    parse_canon_page, deduplicate_urls,
    _context_key, _format_group_content, _build_canon_reference,
    _balanced_split_canons, _emit_group_chunks,
    _book_for, build_documents,
)

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "canon-law")
_vendored = os.path.exists(os.path.join(_SRC, "pages.json"))

SAMPLE_HTML = """<html><body><table><tbody><tr><td>
<p align="center"><b>CODE OF CANON LAW</b></p>
<p>Can. 1 The canons of this Code regard only the Latin Church.</p>
<p>Can. 2 For the most part the Code does not define the rites which must be observed.</p>
<p>Can. 5 §1. Universal or particular customs presently in force which are contrary to the prescripts.</p>
<p>§2. Universal or particular customs beyond the law are preserved.</p>
<p>Can. 6 §1. When this Code takes force, the following are abrogated:</p>
<p>1/ the Code of Canon Law promulgated in 1917;</p>
<p>2/ other universal or particular laws contrary to the prescripts;</p>
</td></tr></tbody></table></body></html>"""

def test_parse_canon_page_extracts_canons():
    canons = parse_canon_page(SAMPLE_HTML)
    assert len(canons) == 4  # Can. 1, 2, 5, 6

def test_parse_canon_strips_can_prefix():
    canons = parse_canon_page(SAMPLE_HTML)
    num, text, _ = canons[0]
    assert num == 1
    assert not text.startswith("Can.")
    assert text.startswith("The canons")

def test_parse_canon_appends_subparagraphs():
    canons = parse_canon_page(SAMPLE_HTML)
    can5 = next(c for c in canons if c[0] == 5)
    assert "§1." in can5[1]
    assert "§2." in can5[1]

def test_parse_canon_appends_numbered_items():
    canons = parse_canon_page(SAMPLE_HTML)
    can6 = next(c for c in canons if c[0] == 6)
    assert "1/" in can6[1]
    assert "2/" in can6[1]

def test_parse_canon_skips_headers():
    canons = parse_canon_page(SAMPLE_HTML)
    texts = [c[1] for c in canons]
    assert not any("CODE OF CANON LAW" in t for t in texts)

def test_deduplicate_urls_strips_fragments():
    urls = [
        "/archive/cic_lib1-cann1-6_en.html",
        "/archive/cic_lib1-cann1-6_en.html#Art._1.",
        "/archive/cic_lib1-cann1-6_en.html#Art._2.",
        "/archive/cic_lib1-cann7-22_en.html",
    ]
    result = deduplicate_urls(urls, base="http://www.vatican.va")
    assert len(result) == 2
    assert "http://www.vatican.va/archive/cic_lib1-cann1-6_en.html" in result
    assert "http://www.vatican.va/archive/cic_lib1-cann7-22_en.html" in result


HIERARCHY_HTML = """<html><body><table><tbody><tr><td>
<p>BOOK II. THE PEOPLE OF GOD</p>
<p>TITLE I. THE OBLIGATIONS AND RIGHTS OF ALL THE CHRISTIAN FAITHFUL</p>
<p>Can. 208 In virtue of their rebirth in Christ, there exists among all the Christian faithful a true equality.</p>
<p>Can. 209 §1. The Christian faithful, even in their own manner of acting, are always obliged to maintain communion with the Church.</p>
<p>§2. With great diligence they are to lead a holy life.</p>
<p>CHAPTER I. OBLIGATIONS AND RIGHTS OF THE CHRISTIAN FAITHFUL</p>
<p>Can. 210 All the faithful must direct their efforts to lead a holy life.</p>
</td></tr></tbody></table></body></html>"""


def test_parse_canon_page_returns_3_tuple():
    canons = parse_canon_page(SAMPLE_HTML)
    assert len(canons) == 4
    num, text, ctx = canons[0]
    assert isinstance(num, int)
    assert isinstance(text, str)
    assert isinstance(ctx, dict)


def test_parse_canon_page_context_has_required_keys():
    canons = parse_canon_page(SAMPLE_HTML)
    _, _, ctx = canons[0]
    assert "book" in ctx
    assert "part" in ctx
    assert "title" in ctx
    assert "chapter" in ctx
    assert "article" in ctx


def test_parse_canon_header_updates_context():
    canons = parse_canon_page(HIERARCHY_HTML)
    can208 = next(c for c in canons if c[0] == 208)
    ctx = can208[2]
    assert "BOOK II" in ctx["book"] or "THE PEOPLE OF GOD" in ctx["book"]
    assert "TITLE I" in ctx["title"] or "OBLIGATIONS" in ctx["title"]


def test_parse_canon_chapter_header_updates_chapter_context():
    canons = parse_canon_page(HIERARCHY_HTML)
    can210 = next(c for c in canons if c[0] == 210)
    ctx = can210[2]
    assert ctx["chapter"] != ""


def test_parse_canon_header_resets_lower_levels():
    """When a TITLE header appears, chapter and article must reset to ''."""
    canons = parse_canon_page(HIERARCHY_HTML)
    can208 = next(c for c in canons if c[0] == 208)
    ctx = can208[2]
    assert ctx["chapter"] == ""
    assert ctx["article"] == ""


def test_context_key_includes_all_levels():
    ctx = {"book": "Book I", "part": "", "title": "Title I", "chapter": "Chapter I", "article": ""}
    key = _context_key(ctx)
    assert key == ("Book I", "", "Title I", "Chapter I", "")


def test_format_group_content_header_and_canons():
    ctx = {"book": "Book II", "part": "", "title": "Title I", "chapter": "", "article": ""}
    canons = [(208, "In virtue of their rebirth in Christ."), (209, "The faithful must act.")]
    content = _format_group_content(ctx, canons)
    assert "Book II" in content
    assert "Title I" in content
    assert "Can. 208:" in content
    assert "Can. 209:" in content


def test_format_group_content_omits_empty_levels():
    ctx = {"book": "Book I", "part": "", "title": "", "chapter": "", "article": ""}
    canons = [(1, "The canons regard only the Latin Church.")]
    content = _format_group_content(ctx, canons)
    assert "Book I" in content
    assert " — \n" not in content


def test_build_canon_reference_multi_canon():
    ctx = {"book": "Book II", "part": "", "title": "Title I", "chapter": "", "article": ""}
    ref = _build_canon_reference(ctx, 208, 223)
    assert "Code of Canon Law" in ref
    assert "Book II" in ref
    assert "208" in ref
    assert "223" in ref


def test_build_canon_reference_single_canon():
    ctx = {"book": "Book I", "part": "", "title": "", "chapter": "", "article": ""}
    ref = _build_canon_reference(ctx, 1, 1)
    assert "Can. 1" in ref
    assert "Cann." not in ref


def test_balanced_split_canons_near_midpoint():
    canons = [(i, "x" * 100) for i in range(1, 11)]  # 10 canons, 100 chars each → 1000 total
    left, right = _balanced_split_canons(canons)
    assert abs(len(left) - len(right)) <= 2


def test_emit_group_chunks_within_ceiling():
    ctx = {"book": "Book I", "part": "", "title": "Title I", "chapter": "", "article": ""}
    canons = [(1, "Short canon text."), (2, "Another short canon.")]
    chunks: list = []
    counter = [0]
    _emit_group_chunks(canons, ctx, chunks, counter)
    assert len(chunks) == 1
    content, ref, pos, meta = chunks[0]
    assert "Can. 1:" in content
    assert "Can. 2:" in content
    assert pos == 0
    assert meta["canon_range"] == [1, 2]


def test_emit_group_chunks_splits_at_ceiling():
    ctx = {"book": "Book I", "part": "", "title": "Title I", "chapter": "", "article": ""}
    big_text = "x " * 800  # ~1600 chars per canon
    canons = [(i, big_text) for i in range(1, 4)]
    chunks: list = []
    counter = [0]
    _emit_group_chunks(canons, ctx, chunks, counter, ceiling=3500)
    assert len(chunks) >= 2
    for content, _, _, _ in chunks:
        assert len(content) <= 3500


def test_emit_group_chunks_cross_refs_extracted():
    ctx = {"book": "Book I", "part": "", "title": "", "chapter": "", "article": ""}
    canons = [(1, "See can. 5 and can. 208 for details.")]
    chunks: list = []
    counter = [0]
    _emit_group_chunks(canons, ctx, chunks, counter)
    _, _, _, meta = chunks[0]
    assert 5 in meta["cross_refs"]
    assert 208 in meta["cross_refs"]


# ── Dual-pipeline build_documents (one passage per canon) ────────────────────

def test_book_for_assigns_by_canon_range():
    assert _book_for(1).startswith("Book I")
    assert _book_for(203).startswith("Book I")
    assert _book_for(204).startswith("Book II")
    assert _book_for(750).startswith("Book III")
    assert _book_for(1752).startswith("Book VII")


@pytest.mark.skipif(not _vendored, reason="canon-law not vendored")
def test_single_document_one_passage_per_canon():
    docs = build_documents()
    assert len(docs) == 1
    d = docs[0]
    assert d.collection == "canon-law"
    units = [p.unit_label for p in d.passages]
    assert len(units) == len(set(units))            # one passage per canon, no dups
    assert all(u.startswith("Can. ") for u in units)
    assert len(units) > 1700


@pytest.mark.skipif(not _vendored, reason="canon-law not vendored")
def test_exactly_seven_books_no_empty_and_breadcrumb():
    d = build_documents()[0]
    books = {p.metadata["book"] for p in d.passages}
    assert len(books) == 7, books
    assert all(b and "?" not in b for b in books)
    assert all(p.chapter_label.startswith("Book ") for p in d.passages)
    for p in d.passages:
        assert p.anchor.startswith("can/")
        assert not p.content.lstrip().startswith("[")
